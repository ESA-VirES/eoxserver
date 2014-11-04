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

from eoxserver.core import Component, implements
import eoxmagmod
import numpy

from vires.interfaces import ForwardModelProviderInterface


class WMMForwardModel(Component):
    """ Forward model calculator for the WMM.
    """

    implements(ForwardModelProviderInterface)

    identifier = "WMM"

    def evaluate(self, data_item, bbox, size_x, size_y, elevation, date):
        model = eoxmagmod.read_model_wmm2010(eoxmagmod.DATA_WMM_2010)
        lons = numpy.linspace(bbox[0], bbox[2], size_x, endpoint=True)
        lats = numpy.linspace(bbox[1], bbox[3], size_y, endpoint=True)
        lons, lats = numpy.meshgrid(lons, lats)

        arr = numpy.empty((size_y, size_x, 3))
        arr[:, :, 0] = lons
        arr[:, :, 1] = lats
        arr[:, :, 2] = elevation

        return model.eval(arr, date)
