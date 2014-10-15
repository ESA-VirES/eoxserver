#-------------------------------------------------------------------------------
# $Id$
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2014 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#-------------------------------------------------------------------------------

from optparse import make_option
from itertools import tee, izip

from django.core.management import call_command
from django.core.management.base import CommandError, BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, utc
from django.contrib.gis import geos
from spacepy import pycdf
from eoxserver.core import env
from eoxserver.backends import models as backends
from eoxserver.backends.component import BackendComponent
from eoxserver.backends.cache import CacheContext
from eoxserver.backends.access import connect
from eoxserver.resources.coverages import models
from eoxserver.resources.coverages.metadata.component import MetadataComponent
from eoxserver.resources.coverages.management.commands import (
    CommandOutputMixIn, _variable_args_cb, nested_commit_on_success
)

from vires.models import Product

def _variable_args_cb_list(option, opt_str, value, parser):
    """ Helper function for optparse module. Allows variable number of option
        values when used as a callback.
    """
    args = []
    for arg in parser.rargs:
        if not arg.startswith('-'):
            args.append(arg)
        else:
            del parser.rargs[:len(args)]
            break
    if not getattr(parser.values, option.dest):
        setattr(parser.values, option.dest, [])

    getattr(parser.values, option.dest).append(args)


class Command(CommandOutputMixIn, BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option("-i", "--identifier", "--coverage-id", dest="identifier",
            action="store", default=None,
            help=("Override identifier.")
        ),
        make_option("-d", "--data", dest="data",
            action="callback", callback=_variable_args_cb_list, default=[],
            help=("Add a data item to the dataset. Format is: "
                  "[storage_type:url] [package_type:location]* format:location"
                 )
        ),
        make_option("-s", "--semantic", dest="semantics",
            action="callback", callback=_variable_args_cb, default=None,
            help=("Optional band semantics. If given, one band "
                  "semantics 'band[*]' must be present for each '--data' "
                  "option.")
        ),
        make_option("-m", "--meta-data", dest="metadata",
            action="callback", callback=_variable_args_cb_list, default=[],
            help=("Optional. [storage_type:url] [package_type:location]* "
                  "format:location")
        ),
        make_option("-r", "--range-type", dest="range_type_name",
            help=("Mandatory. Name of the stored range type. ")
        ),

        make_option("--size", dest="size",
            action="store", default=None,
            help=("Override size. Comma separated list of <size-x>,<size-y>.")
        ),

        make_option("--begin-time", dest="begin_time",
            action="store", default=None,
            help=("Override begin time. Format is ISO8601 datetime strings.")
        ),

        make_option("--end-time", dest="end_time",
            action="store", default=None,
            help=("Override end time. Format is ISO8601 datetime strings.")
        ),

        make_option("--visible", dest="visible",
            action="store_true", default=False,
            help=("Set the coverage to be 'visible', which means it is "
                  "advertised in GetCapabilities responses.")
        ),

        make_option("--collection", dest="collection_ids",
            action='callback', callback=_variable_args_cb, default=None,
            help=("Optional. Link to one or more collection(s).")
        ),

        make_option('--ignore-missing-collection',
            dest='ignore_missing_collection',
            action="store_true", default=False,
            help=("Optional. Proceed even if the linked collection "
                  "does not exist. By defualt, a missing collection "
                  "will result in an error.")
        )
    )

    args = (
        "-d [<storage>:][<package>:]<location> [-d ... ] "
        "-r <range-type-name> "
        "[-m [<storage>:][<package>:]<location> [-m ... ]] "
        "[-s <semantic> [-s <semantic>]] "
        "[--identifier <identifier>] "
        "[-e <minx>,<miny>,<maxx>,<maxy>] "
        "[--size <size-x> <size-y>] "
        "[--srid <srid> | --projection <projection-def>] "
        "[--footprint <footprint-wkt>] "
        "[--begin-time <begin-time>] [--end-time <end-time>] "
        "[--coverage-type <coverage-type-name>] "
        "[--visible] [--collection <collection-id> [--collection ... ]] "
        "[--ignore-missing-collection]"
    )

    help = """
        Registers a Dataset.
        A dataset is a collection of data and metadata items. When beeing
        registered, as much metadata as possible is extracted from the supplied
        (meta-)data items. If some metadata is still missing, it needs to be
        supplied via the specific override options.

        By default, datasets are not "visible" which means that they are not
        advertised in the GetCapabilities sections of the various services.
        This needs to be overruled via the `--visible` switch.

        The registered dataset can optionally be directly inserted one or more
        collections.
    """

    @nested_commit_on_success
    def handle(self, *args, **kwargs):
        with CacheContext() as cache:
            self.handle_with_cache(cache, *args, **kwargs)

    def handle_with_cache(self, cache, *args, **kwargs):
        metadata_component = MetadataComponent(env)
        datas = kwargs["data"]
        semantics = kwargs.get("semantics")
        metadatas = kwargs["metadata"]
        range_type_name = kwargs["range_type_name"]

        if range_type_name is None:
            raise CommandError("No range type name specified.")
        range_type = models.RangeType.objects.get(name=range_type_name)

        metadata_keys = set((
            "identifier", "extent", "size", "ground_path",
            "footprint", "begin_time", "end_time",
        ))

        all_data_items = []
        retrieved_metadata = {}

        retrieved_metadata.update(
            self._get_overrides(**kwargs)
        )

        for metadata in metadatas:
            storage, package, format, location = self._get_location_chain(
                metadata
            )
            data_item = backends.DataItem(
                location=location, format=format or "", semantic="metadata",
                storage=storage, package=package,
            )
            data_item.full_clean()
            data_item.save()
            all_data_items.append(data_item)

            with open(connect(data_item, cache)) as f:
                content = f.read()
                reader = metadata_component.get_reader_by_test(content)
                if reader:
                    values = reader.read(content)

                    format = values.pop("format", None)
                    if format:
                        data_item.format = format
                        data_item.full_clean()
                        data_item.save()

                    for key, value in values.items():
                        if key in metadata_keys:
                            retrieved_metadata.setdefault(key, value)

        if len(datas) < 1:
            raise CommandError("No data files specified.")

        if semantics is None:
            # TODO: check corner cases.
            # e.g: only one data item given but multiple bands in range type
            # --> bands[1:<bandnum>]
            if len(datas) == 1:
                if len(range_type) == 1:
                    semantics = ["bands[1]"]
                else:
                    semantics = ["bands[1:%d]" % len(range_type)]

            else:
                semantics = ["bands[%d]" % i for i in range(len(datas))]

        for data, semantic in zip(datas, semantics):
            storage, package, format, location = self._get_location_chain(data)
            data_item = backends.DataItem(
                location=location, format=format or "", semantic=semantic,
                storage=storage, package=package,
            )
            data_item.full_clean()
            data_item.save()
            all_data_items.append(data_item)


            # TODO: read meta-data
            ds = pycdf.CDF(connect(data_item, cache))
            reader = VirESMetadataReader()
            if reader:
                values = reader.read(ds)

                format = values.pop("format", None)
                if format:
                    data_item.format = format
                    data_item.full_clean()
                    data_item.save()

                for key, value in values.items():
                    if key in metadata_keys:
                        retrieved_metadata.setdefault(key, value)
            ds = None

        if len(metadata_keys - set(retrieved_metadata.keys())):
            raise CommandError(
                "Missing metadata keys %s."
                % ", ".join(metadata_keys - set(retrieved_metadata.keys()))
            )

        try:
            coverage = Product()
            coverage.range_type = range_type
            coverage.srid = 4326
            coverage.extent = (-180, -90, 180, 90)

            for key, value in retrieved_metadata.items():
                setattr(coverage, key, value)

            coverage.visible = kwargs["visible"]

            coverage.full_clean()
            coverage.save()

            for data_item in all_data_items:
                data_item.dataset = coverage
                data_item.full_clean()
                data_item.save()

            # link with collection(s)
            if kwargs["collection_ids"]:
                ignore_missing_collection = kwargs["ignore_missing_collection"]
                call_command("eoxs_collection_link",
                    collection_ids=kwargs["collection_ids"],
                    add_ids=[coverage.identifier],
                    ignore_missing_collection=ignore_missing_collection
                )

        except Exception as e:
            self.print_traceback(e, kwargs)
            raise CommandError("Dataset registration failed: %s" % e)

        self.print_msg(
            "Dataset with ID '%s' registered sucessfully."
            % coverage.identifier
        )

    def _get_overrides(self, identifier=None, size=None, extent=None,
                       begin_time=None, end_time=None, footprint=None,
                       projection=None, coverage_type=None, **kwargs):

        overrides = {}

        if coverage_type:
            overrides["coverage_type"] = coverage_type

        if identifier:
            overrides["identifier"] = identifier

        if extent:
            overrides["extent"] = map(float, extent.split(","))

        if size:
            overrides["size"] = int(size)

        if begin_time:
            overrides["begin_time"] = parse_datetime(begin_time)

        if end_time:
            overrides["end_time"] = parse_datetime(end_time)

        if footprint:
            footprint = geos.GEOSGeometry(footprint)
            if footprint.hasz:
                raise CommandError(
                    "Invalid footprint geometry! 3D geometry is not supported!"
                )
            if footprint.geom_type == "MultiPolygon":
                overrides["footprint"] = footprint
            elif footprint.geom_type == "Polygon":
                overrides["footprint"] = geos.MultiPolygon(footprint)
            else:
                raise CommandError(
                    "Invalid footprint geometry type '%s'!"
                    % (footprint.geom_type)
                )

        if projection:
            try:
                overrides["projection"] = int(projection)
            except ValueError:
                overrides["projection"] = projection

        return overrides

    def _get_location_chain(self, items):
        """ Returns the tuple
        """
        component = BackendComponent(env)
        storage = None
        package = None

        storage_type, url = self._split_location(items[0])
        if storage_type:
            storage_component = component.get_storage_component(storage_type)
        else:
            storage_component = None

        if storage_component:
            storage, _ = backends.Storage.objects.get_or_create(
                url=url, storage_type=storage_type
            )

        # packages
        for item in items[1 if storage else 0:-1]:
            type_or_format, location = self._split_location(item)
            package_component = component.get_package_component(type_or_format)
            if package_component:
                package, _ = backends.Package.objects.get_or_create(
                    location=location, format=format,
                    storage=storage, package=package
                )
                storage = None  # override here
            else:
                raise Exception(
                    "Could not find package component for format '%s'"
                    % type_or_format
                )

        format, location = self._split_location(items[-1])
        return storage, package, format, location

    def _split_location(self, item):
        """ Splits string as follows: <format>:<location> where format can be
            None.
        """
        p = item.find(":")
        if p == -1:
            return None, item
        return item[:p], item[p + 1:]


def save(model):
    model.full_clean()
    model.save()
    return model


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


class VirESMetadataReader(object):
    def read(self, ds):
        previous_lon = None
        current = []
        path = []
        for lon, lat in izip(ds["Longitude"][:], ds["Latitude"][:]):
            #print lon, lat
            if previous_lon is not None and lon < previous_lon \
                    and (previous_lon - lon) > 1.:
                if current:
                    try:
                        path.append(geos.LineString(current))
                    except:
                        print current
                        raise
                current = []
            current.append((lon, lat))
            previous_lon = lon

        ground_path = geos.MultiLineString(path).simplify(0.01)

        return {
            "begin_time": make_aware(ds["Timestamp"][0], utc),
            "end_time": make_aware(ds["Timestamp"][-1], utc),
            "ground_path": ground_path,
            "footprint": geos.MultiPolygon(ground_path.buffer(0.01)),
            "format": "CDF",
            "size": (len(ds["Timestamp"]), 0),
            "extent": ground_path.extent
        }
