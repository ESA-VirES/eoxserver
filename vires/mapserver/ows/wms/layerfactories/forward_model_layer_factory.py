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

from eoxserver.core.util.iteratortools import pairwise_iterative
from eoxserver.contrib import mapserver as ms
from eoxserver.services.mapserver.wms.layerfactories.base import (
    BaseCoverageLayerFactory
)

from vires import models


class ForwardModelLayerFactory(BaseCoverageLayerFactory):
    handles = (models.ForwardModel,)
    suffixes = (None,)
    requires_connection = True

    def generate(self, eo_object, group_layer, suffix, options):
        forward_model = eo_object.cast()
        extent = forward_model.extent

        data_items = forward_model.data_items.filter(semantic="coefficients")
        #range_type = forward_model.range_type

        #offsite = self.offsite_color_from_range_type(range_type)
        #options = self.get_render_options(coverage)

        layer = self._create_layer(
            forward_model, forward_model.identifier, extent
        )
        #self.set_render_options(layer, offsite, options)
        self._apply_styles(layer, 0, 256)
        yield layer, data_items

    def _apply_styles(self, layer, minvalue, maxvalue):
        def create_style(name, layer, colors, minvalue, maxvalue):
            cls = ms.classObj()
            cls.group = name
            step = (maxvalue - minvalue) / float(len(colors) - 1)

            for i, (color_a, color_b) in enumerate(pairwise_iterative(colors)):
                style = ms.styleObj()
                style.mincolor = color_a
                style.maxcolor = color_b

                style.minvalue = minvalue + i * step
                style.maxvalue = minvalue + (i + 1) * step

                style.rangeitem = ""

                cls.insertStyle(style)
            layer.insertClass(cls)

        create_style("rainbow", layer, (
            ms.colorObj(127, 0, 127),  # lila
            ms.colorObj(0, 0, 255),    # blue
            ms.colorObj(0, 255, 255),  # light blue
            ms.colorObj(255, 255, 0),  # yellow
            ms.colorObj(255, 127, 0),  # orange
            ms.colorObj(255, 0, 0),    # red
        ), minvalue, maxvalue)

        create_style("jet", layer, (
            ms.colorObj(0, 0, 144),
            ms.colorObj(0, 15, 255),
            ms.colorObj(0, 144, 255),
            ms.colorObj(15, 255, 238),
            ms.colorObj(144, 255, 112),
            ms.colorObj(255, 238, 0),
            ms.colorObj(255, 112, 0),
            ms.colorObj(238, 0, 0),
            ms.colorObj(127, 0, 0),
        ), minvalue, maxvalue)