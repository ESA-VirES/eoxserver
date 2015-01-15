#-------------------------------------------------------------------------------
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Daniel Santillan <daniel.santillan@eox.at>
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

import os 
from uuid import uuid4
import os.path
import base64
import struct
import datetime as dt
import time
from itertools import izip
from lxml import etree
from StringIO import StringIO
try:
    # available in Python 2.7+
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict
import numpy as np

from eoxserver.core import Component, implements
from eoxserver.services.ows.wps.interfaces import ProcessInterface
from eoxserver.services.ows.wps.exceptions import InvalidOutputDefError
from eoxserver.services.result import ResultBuffer, ResultFile
from eoxserver.services.ows.wps.parameters import (
    ComplexData, CDObject, CDTextBuffer, CDFile, 
    FormatText, FormatXML, FormatJSON, FormatBinaryRaw, FormatBinaryBase64,
    BoundingBoxData, BoundingBox,
    LiteralData, String,
    AllowedRange, UnitLinear,
)



from vires.util import get_total_seconds

import eoxmagmod as mm
from eoxmagmod import (
    GEODETIC_ABOVE_WGS84, GEOCENTRIC_SPHERICAL, GEOCENTRIC_CARTESIAN, convert, vrot_sph2cart, vnorm,
)

import matplotlib.cm
from matplotlib.colors import LinearSegmentedColormap
import tempfile
os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import matplotlib as mpl
mpl.use('Agg')
from matplotlib import pyplot



def toYearFraction(dt_start, dt_end):
    def sinceEpoch(date): # returns seconds since epoch
        return time.mktime(date.timetuple())

    date = (dt_end - dt_start)/2 + dt_start  
    s = sinceEpoch

    year = date.year
    startOfThisYear = dt.datetime(year=year, month=1, day=1)
    startOfNextYear = dt.datetime(year=year+1, month=1, day=1)

    yearElapsed = s(date) - s(startOfThisYear)
    yearDuration = s(startOfNextYear) - s(startOfThisYear)
    fraction = yearElapsed/yearDuration

    return date.year + fraction


class load_shc(Component):
    """ Process to retrieve registered data (focused on Swarm data)
    """
    implements(ProcessInterface)

    identifier = "load_shc"
    title = "Load and process SHC coefficient file returning image of resulting harmonic expansion"
    metadata = {"test-metadata":"http://www.metadata.com/test-metadata"}
    profiles = ["test_profile"]

    inputs = [
        ("shc", ComplexData('shc',
                title="SHC file data",
                abstract="SHC file data to be processed.",
                formats=(FormatText('text/plain')
            )
        )),
        ("begin_time", LiteralData('begin_time', dt.datetime, optional=False,
            abstract="Start of the time interval",
        )),
        ("end_time", LiteralData('end_time', dt.datetime, optional=False,
            abstract="End of the time interval",
        )),
        ("band", LiteralData('band', str, optional=True,
            default="F", abstract="Band wished to be visualized",
        )),
        ("dim_range", LiteralData('dim_range', str, optional=True,
            default="30000,60000", abstract="Range dimension for visualized parameter",
        )),
        ("style", LiteralData('style', str, optional=True,
            default="jet", abstract="Colormap to be applied to visualization",
        )),
    ]


    outputs = [
        ("output",
            ComplexData('output',
                title="Spehrical expansion result image",
                abstract="Returns the styled result image of the spherical expansion as png",
                formats=(
                    FormatBinaryBase64('image/png'),
                    FormatBinaryRaw('image/png'),
                )
            )
        ),
    ]

    def execute(self, shc, begin_time, end_time, band, dim_range, style, output, **kwarg):
        outputs = {}

        cdict = {
            'red': [],
            'green': [],
            'blue': [],
        }

        clist = [
            (0.0,[150,0,90]),
            (0.125,[0,0,200]),
            (0.25,[0,25,255]),
            (0.375,[0,152,255]),
            (0.5,[44,255,150]),
            (0.625,[151,255,0]),
            (0.75,[255,234,0]),
            (0.875,[255,111,0]),
            (1.0,[255,0,0]),
        ]

        for x, (r, g, b) in clist:
            r = r / 255.
            g = g / 255.
            b = b / 255.
            cdict["red"].append((x, r, r))
            cdict["green"].append((x, g, g))
            cdict["blue"].append((x, b, b))

        rainbow = LinearSegmentedColormap('rainbow', cdict)


        if style == "rainbow":
            style = rainbow

        model = mm.read_model_shc(shc)

        dlat = 0.5
        dlon = 0.5

        height = 0  
        lat = np.linspace(90.0,-90.0,int(1+180/dlat))
        lon = np.linspace(-180.0,180.0,int(1+360/dlon))

        print lat.size, lon.size 

        coord_wgs84 = np.empty((lat.size, lon.size, 3))
        coord_wgs84[:,:,1], coord_wgs84[:,:,0] = np.meshgrid(lon, lat)
        coord_wgs84[:,:,2] = height

        # evaluate the model 
        maxdegree = -1 
        mindegree = -1 

        date = toYearFraction(begin_time, end_time)

        m_ints3 = vnorm(model.eval(coord_wgs84, date, GEODETIC_ABOVE_WGS84, GEODETIC_ABOVE_WGS84,
            secvar=False, maxdegree=maxdegree, mindegree=mindegree, check_validity=False))

        # calculate inclination, declination, intensity
        #m_inc, m_dec, m_ints3 = vincdecnorm(m_field)

        # the output image
        basename = "%s_%s"%( "shc_result-",uuid4().hex )
        filename_png = "/tmp/%s.png" %( basename )

        try:
            #fig = pyplot.imshow(pix_res,interpolation='nearest')
            #fig = pyplot.imshow(m_field,vmin=dim_range[0], vmax=dim_range[1], interpolation='nearest')
            fig = pyplot.imshow(m_ints3, vmin=dim_range[0], vmax=dim_range[1], interpolation='nearest')
            fig.set_cmap(style)
            fig.write_png(filename_png, True)

            result = CDFile(filename_png, **output)

            # with open(filename_png) as f:
            #     output = f.read()

        except Exception as e: 

            if os.path.isfile(filename_png):
                os.remove(filename_png)

            raise e
           
        # else:
        #     os.remove(filename_png)

        #return base64.b64encode(output)
        
        outputs['output'] = result

        return outputs


