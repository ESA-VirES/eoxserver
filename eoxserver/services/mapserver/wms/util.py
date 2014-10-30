#-------------------------------------------------------------------------------
# $Id$
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2011 EOX IT Services GmbH
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


import logging
from itertools import chain

from django.db.models import Q
from django.utils.datastructures import SortedDict

from eoxserver.core import Component, ExtensionPoint
from eoxserver.core.config import get_eoxserver_config
from eoxserver.contrib import mapserver as ms
from eoxserver.resources.coverages.crss import CRSsConfigReader
from eoxserver.services.mapserver.interfaces import (
    ConnectorInterface, LayerFactoryInterface, StyleApplicatorInterface
)
from eoxserver.services.result import result_set_from_raw_data, get_content_type, ResultBuffer, ResultFile
from eoxserver.services.exceptions import RenderException
from eoxserver.services.ows.wms.exceptions import InvalidCRS, InvalidFormat




import os
import tempfile
os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import matplotlib as mpl
mpl.use('Agg')
from matplotlib import pyplot
from uuid import uuid4
import datetime as dt
import numpy as np
import math

from spacepy import pycdf
from eoxserver.backends.access import connect
from vires import models
from vires.util import get_total_seconds


try:
    # available in Python 2.7+
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict

def savefig_pix(fig,fname,width,height,dpi=100, transparent=True):
    rdpi = 1.0/float(dpi)  
    fig.set_size_inches(width*rdpi,height*rdpi)
    fig.savefig(fname, dpi=dpi, transparent=transparent)

logger = logging.getLogger(__name__)


class MapServerWMSBaseComponent(Component):
    """ Base class for various WMS render components using MapServer.
    """

    connectors = ExtensionPoint(ConnectorInterface)
    layer_factories = ExtensionPoint(LayerFactoryInterface)
    style_applicators = ExtensionPoint(StyleApplicatorInterface)


    @property
    def suffixes(self):
        return ['_measurement',] + self._suffixes

    def render(self, layer_groups, request_values, **options):


        measurement = False

        for _, _, _, suffix in tuple(layer_groups.walk()):
            if suffix == "_measurement":
                return self.my_render(layer_groups, request_values, **options)
        else:
            return self._render(layer_groups, request_values, **options)
        

    def my_render(self, layer_groups, request_values, **options):

        # the output image
        basename = "%s_%s"%( "tmp",uuid4().hex )
        filename_png = "/tmp/%s.png" %( basename )

        value_dict = dict(request_values)
        options_dict = dict(options)

        resolution = 10

        
        begin_time = options_dict["time"].low
        end_time = options_dict["time"].high
        bbox = [float(x) for x in value_dict["BBOX"].split(",")]
        
        output_data = OrderedDict()
        tmp_data = OrderedDict()


        for collections, coverage, name, suffix in layer_groups.walk():
            
            if coverage:

                cov_cast = coverage.cast()

                # Open file
                filename = connect(cov_cast.data_items.all()[0])

                ds = pycdf.CDF(filename)
                
                cov_begin_time, cov_end_time = coverage.time_extent
                
                t_res = get_total_seconds(cov_cast.resolution_time)
                low = max(0, int(get_total_seconds(begin_time - cov_begin_time) / t_res))
                high = min(cov_cast.size_x, int(math.ceil(get_total_seconds(end_time - cov_begin_time) / t_res)))

                # Read data
                for band in ["Latitude", "Longitude", "F"]:
                    data = ds[band]
                    tmp_data[band] = data[low:high:resolution]

                if bbox:
                    lons = tmp_data["Longitude"]
                    lats = tmp_data["Latitude"]
                    mask = (lons > bbox[0]) & (lons < bbox[2]) & (lats > bbox[1]) & (lats < bbox[3])

                    for name, data in tmp_data.items():
                        tmp_data[name] = tmp_data[name][mask]

                for band in ["Latitude", "Longitude", "F"]:
                    if band in output_data:
                        output_data[band] = np.concatenate([output_data[band], tmp_data[band]])
                    else:
                        output_data[band] = tmp_data[band]

        
        try:



            x = output_data["Longitude"]
            y = output_data["Latitude"]

            fg = pyplot.figure() 
            ax = pyplot.subplot(111)

            #pl = pyplot.plot( x, y ) 
            pyplot.scatter(output_data["Longitude"], output_data["Latitude"], c=output_data["F"], s=35, vmin=30000, vmax=60000, edgecolors='none')
            pyplot.xlim(bbox[0], bbox[2])
            pyplot.ylim(bbox[1], bbox[3])
            pyplot.axis("off")
            fg.subplots_adjust(wspace=0, hspace=0, left=0, right=1, bottom=0, top=1)

            savefig_pix(fg, filename_png, int(value_dict["WIDTH"]), int(value_dict["HEIGHT"]), dpi=100)




            # fig = pyplot.figure()
            # pyplot.scatter(output_data["Longitude"], output_data["Latitude"], c=output_data["F"], s=35, vmin=20000, vmax=100000)
            #fig = pyplot.imshow(pix_res,vmin=-res_, vmax=res_, interpolation='nearest')
            #fig.set_cmap('RdBu')
            #fig.write_png(filename_png, True)
            # fig.savefig(filename_png)

            # with open(filename_png) as f:
            #     output = f.read()

        except Exception as e: 

            if os.path.isfile(filename_png):
                os.remove(filename_png)

            raise
           
#        else:
#            os.remove(filename_png)

        return [ResultFile(filename_png, "image/png")], "image/png"
        #return [ResultBuffer("Hello world! \n%s\n%s\n%s"%(tuple(layer_groups.walk()), request_values, options), "text/plain")], "text/plain"

    def _render(self, layer_groups, request_values, **options):
        map_ = ms.Map()
        map_.setMetaData("ows_enable_request", "*")
        map_.setProjection("EPSG:4326")
        map_.imagecolor.setRGB(0, 0, 0)

        symbol = ms.symbolObj("circle")
        symbol.type = ms.MS_SYMBOL_ELLIPSE
        line = ms.lineObj()
        point = ms.pointObj(1,1)
        line.add(point)
        symbol.setPoints(line)
        symbol.filled = ms.MS_TRUE
        

        #ss = ms.symbolSetObj()
        
        #ss.appendSymbol(symbol)

        map_.symbolset.appendSymbol(symbol)

        #import pdb; pdb.set_trace()

        # set supported CRSs
        decoder = CRSsConfigReader(get_eoxserver_config())
        crss_string = " ".join(
            map(lambda crs: "EPSG:%d" % crs, decoder.supported_crss_wms)
        )
        map_.setMetaData("ows_srs", crss_string)
        map_.setMetaData("wms_srs", crss_string)

        self.check_parameters(map_, request_values)

        session = self.setup_map(layer_groups, map_, options)
        
        with session:
            request = ms.create_request(request_values)
            raw_result = map_.dispatch(request)

            result = result_set_from_raw_data(raw_result)
            return result, get_content_type(result)


    def check_parameters(self, map_, request_values):
        for key, value in request_values:
            if key.lower() == "format":
                if not map_.getOutputFormatByName(value):
                    raise InvalidFormat(value)
                break
        else:
            raise RenderException("Missing 'format' parameter")        

    @property
    def _suffixes(self):
        return list(
            chain(*[factory.suffixes for factory in self.layer_factories])
        )


    def get_connector(self, data_items):
        for connector in self.connectors:
            if connector.supports(data_items):
                return connector
        return None


    def get_layer_factory(self, suffix):
        result = None
        for factory in self.layer_factories:
            if suffix in factory.suffixes:
                if result:
                    pass # TODO
                    #raise Exception("Found")
                result = factory
                return result
        return result


    def setup_map(self, layer_selection, map_, options):
        group_layers = SortedDict()
        session = ConnectorSession()

        # set up group layers before any "real" layers
        for collections, _, name, suffix in tuple(layer_selection.walk()):
            if not collections:
                continue

            # get a factory for the given suffix
            factory = self.get_layer_factory(suffix)
            if not factory:
                # raise or pass?
                continue

            # get the groups name, which is the name of the collection + the 
            # suffix
            group_name = collections[-1].identifier + (suffix or "")

            # generate a group layer
            group_layer = factory.generate_group(group_name)
            group_layers[group_name] = group_layer

        # set up the actual layers for each coverage
        for collections, coverage, name, suffix in layer_selection.walk():
            # get a factory for the given coverage and suffix
            factory = self.get_layer_factory(suffix)

            group_layer = None
            group_name = None

            if collections:
                group_name = collections[-1].identifier + (suffix or "")
                group_layer = group_layers.get(group_name)

            if not coverage:
                # add an empty layer to not produce errors out of bounds.
                if name:
                    tmp_layer = ms.layerObj()
                    tmp_layer.name = (name + suffix) if suffix else name
                    layers_and_data_items = ((tmp_layer, ()),)
                else:
                    layers_and_data_items = ()

            elif not factory:
                tmp_layer = ms.layerObj()
                tmp_layer.name = name
                layers_and_data_items = ((tmp_layer, ()),)
            else:
                data_items = coverage.data_items.all()
                coverage.cached_data_items = data_items
                layers_and_data_items = tuple(factory.generate(
                    coverage, group_layer, suffix, options
                ))

            for layer, data_items in layers_and_data_items:
                connector = self.get_connector(data_items)
                
                if group_name:
                    layer.setMetaData("wms_layer_group", "/" + group_name)

                session.add(connector, coverage, data_items, layer)
                

        coverage_layers = [layer for _, layer, _ in session.coverage_layers]
        for layer in chain(group_layers.values(), coverage_layers):
            old_layer = map_.getLayerByName(layer.name)
            if old_layer:
                # remove the old layer and reinsert the new one, to 
                # raise the layer to the top.
                # TODO: find a more efficient way to do this
                map_.removeLayer(old_layer.index)
            map_.insertLayer(layer)

        # apply any styles
        # TODO: move this to map/legendgraphic renderer only?
        for coverage, layer, data_items in session.coverage_layers:
            for applicator in self.style_applicators:
                applicator.apply(coverage, data_items, layer)

        return session


    def get_empty_layers(self, name):
        layer = ms.layerObj()
        layer.name = name
        layer.setMetaData("wms_enable_request", "getmap")
        return (layer,)


class ConnectorSession(object):
    """ Helper class to be used in `with` statements. Allows connecting and 
        disconnecting all added layers with the given data items.
    """
    def __init__(self):
        self.item_list = []

    def add(self, connector, coverage, data_items, layer):
        self.item_list.append(
            (connector, coverage, layer, data_items)
        )

    def __enter__(self):
        for connector, coverage, layer, data_items in self.item_list:
            if connector:
                connector.connect(coverage, data_items, layer)

    def __exit__(self, *args, **kwargs):
        for connector, coverage, layer, data_items in self.item_list:
            if connector:
                connector.disconnect(coverage, data_items, layer)


    @property
    def coverage_layers(self):
        return map(lambda it: (it[1], it[2], it[3]), self.item_list)
