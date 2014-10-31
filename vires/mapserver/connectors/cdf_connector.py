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

from itertools import izip

from spacepy import pycdf

from eoxserver.core import Component, implements
from eoxserver.backends.access import connect
from eoxserver.contrib import mapserver as ms
from eoxserver.services.mapserver.interfaces import ConnectorInterface


class CDFConnector(Component):
    """ Connects a CDF file.
    """

    implements(ConnectorInterface)

    def supports(self, data_items):
        return (
            len(data_items) == 1 and
            data_items[0].format == "CDF"
        )

    def connect(self, coverage, data_items, layer):
        """
        """

        # TODO: move this to another method
        symbolset = layer.map.symbolset
        #if symbolset.index('circle') == -1:
        symbol = ms.symbolObj('')
        symbol.type = ms.MS_SYMBOL_ELLIPSE
        symbol.name = "circle"
        symbol.filled = ms.MS_TRUE
        symbol.antialiased = ms.MS_TRUE
        symbolset.appendSymbol(symbol)

        #layer.map.setSymbolSet(symbolset)

        ds = pycdf.CDF(connect(data_items[0]))
        band = layer.metadata.get("eoxs_band")
        iteration = izip(
            ds["Longitude"][::20],
            ds["Latitude"][::20],
            ds[band][::20]
        )

        for lon, lat, value in iteration:
            point = ms.pointObj(lon, lat)
            shape = point.toShape()
            shape.initValues(1)
            shape.setValue(0, str(value))

            layer.addFeature(shape)

    def disconnect(self, coverage, data_items, layer):
        """
        """
