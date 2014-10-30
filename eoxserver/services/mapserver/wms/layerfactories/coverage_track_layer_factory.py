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


from eoxserver.core import Component, implements
from eoxserver.contrib.mapserver import (
    Layer, MS_LAYER_POLYGON, shapeObj, classObj, styleObj, colorObj
)
from eoxserver.resources.coverages import models
from vires import models as vires_models
from eoxserver.services.mapserver.interfaces import LayerFactoryInterface
from eoxserver.services.mapserver.wms.layerfactories.base import (
    AbstractLayerFactory, BaseStyleMixIn, PolygonLayerMixIn, LineFeatureLayerMixIn
)

from spacepy import pycdf
from eoxserver.backends.access import connect
from vires import models
from vires.util import get_total_seconds


class CoverageTrackLayerFactory(BaseStyleMixIn, LineFeatureLayerMixIn, AbstractLayerFactory):
    handles = (vires_models.Product, vires_models.ProductCollection)
#    handles = (models.RectifiedDataset, models.ReferenceableDataset,
#               models.RectifiedStitchedMosaic,)
    suffixes = ("_track",)
    requires_connection = False

    
    def generate(self, eo_object, group_layer, suffix, options):
        # don't generate any layers, but add the footprint as feature to the 
        # group layer

        if group_layer:
            layer = group_layer
        else:
            layer = self._create_line_layer(
                eo_object.identifier + "_track"
            )


        # coverage = eo_object.cast()
        # filename = connect(coverage.data_items.all()[0])

        # ds = pycdf.CDF(filename)
        
        # # Read data
        # latitudes = ds["Latitude"][::1000]
        # longitudes = ds["Longitude"][::1000]
       
        # for lat, lon in zip(latitudes, longitudes):
        #     shape = shapeObj.fromWKT("POINT (%s %s)"%(lat,lon))
        #     shape.initValues(1)
        #     shape.setValue(0, eo_object.identifier)
        #     layer.addFeature(shape)



        shape = shapeObj.fromWKT(eo_object.ground_path.wkt)
        shape.initValues(1)
        shape.setValue(0, eo_object.identifier)
        layer.addFeature(shape)
        
        if not group_layer:
            yield layer, ()


    def generate_group(self, name):
        layer = self._create_line_layer(name)

        # Dummy feature, or else empty groups will produce errors
        shape = shapeObj()
        shape.initValues(1)
        shape.setValue(0, "dummy")
        layer.addFeature(shape)

        return layer
