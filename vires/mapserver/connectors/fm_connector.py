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

from os.path import join
from uuid import uuid4
import logging
import time

from django.contrib.gis import geos
from eoxserver.core import Component, implements, ExtensionPoint
from eoxserver.core.util.perftools import log_duration
from eoxserver.contrib import vsi, gdal
from eoxserver.backends.access import connect
from eoxserver.contrib import mapserver as ms
from eoxserver.services.mapserver.interfaces import ConnectorInterface

from vires.util import get_total_seconds
from vires.interfaces import ForwardModelProviderInterface


logger = logging.getLogger(__name__)

class ForwardModelConnector(Component):
    """ Connects a CDF file.
    """

    implements(ConnectorInterface)

    model_providers = ExtensionPoint(ForwardModelProviderInterface)

    def supports(self, data_items):
        return (
            len(data_items) == 1 and
            data_items[0].semantic == "coefficients"
        )

    def connect(self, coverage, data_items, layer, options):
        """
        """

        data_item = data_items[0]
        for model_provider in self.model_providers:
            if model_provider.identifier == data_item.format:
                break
        else:
            raise Exception(
                "No model provider '%s' available." % data_item.format
            )

        # TODO: get bbox, get feature, get elevation, get time
        time = options.get("time")
        elevation = options.get("elevation") or 0
        subsets = options.get("subsets")
        bands = options.get("bands", ("F",))

        # TODO: get size from parameters
        size_x, size_y = options["width"], options["height"]

        bbox = subsets.xy_bbox
        if subsets.srid != 4326:
            bbox = geos.Polygon.from_bbox(bbox).transform(4326).extent

        with log_duration("model evaluation", logger):
            array = model_provider.evaluate(
                data_item, bands[0], bbox, size_x, size_y, elevation, time.value
            )

            range_min, range_max = 22000, 69000
            data_range = options["dimensions"].get("range")
            if data_range:
                try:
                    range_min, range_max = map(float, data_range[0].split(","))
                except:
                    raise Exception("Invalid data range provided.")

            array = (array - range_min) / (range_max - range_min) * 255

        path = join("/vsimem", uuid4().hex)
        #path = "/tmp/fm_output.tif"
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(path, size_x, size_y, 1, gdal.GDT_Byte)

        gt = (
            bbox[0],
            float(bbox[2] - bbox[0]) / size_x,
            0,
            bbox[3],
            0,
            -float(bbox[3] - bbox[1]) / size_y
        )

        ds.SetGeoTransform(gt)

        band = ds.GetRasterBand(1)
        band.WriteArray(array)
        layer.data = path

    def disconnect(self, coverage, data_items, layer, options):
        """
        """

        vsi.remove(layer.data)
