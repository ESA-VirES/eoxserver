#-------------------------------------------------------------------------------
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Martin Paces <martin.paces@eox.at>
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

import json
import csv
import math
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
    ComplexData, CDObject, CDTextBuffer,
    FormatText, FormatXML, FormatJSON, #FormatBinaryRaw, FormatBinaryBase64,
    BoundingBoxData, BoundingBox,
    LiteralData, String,
    AllowedRange, UnitLinear,
)

from uuid import uuid4
from spacepy import pycdf
from eoxserver.backends.access import connect
from vires import models
from vires.util import get_total_seconds

import eoxmagmod as mm
import matplotlib.cm

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

GMM = mm.read_model_wmm2010()

CRSS = (
    4326,  # WGS84
    32661, 32761,  # WGS84 UPS-N and UPS-S
    32601, 32602, 32603, 32604, 32605, 32606, 32607, 32608, 32609, 32610,  # WGS84 UTM  1N-10N
    32611, 32612, 32613, 32614, 32615, 32616, 32617, 32618, 32619, 32620,  # WGS84 UTM 11N-20N
    32621, 32622, 32623, 32624, 32625, 32626, 32627, 32628, 32629, 32630,  # WGS84 UTM 21N-30N
    32631, 32632, 32633, 32634, 32635, 32636, 32637, 32638, 32639, 32640,  # WGS84 UTM 31N-40N
    32641, 32642, 32643, 32644, 32645, 32646, 32647, 32648, 32649, 32650,  # WGS84 UTM 41N-50N
    32651, 32652, 32653, 32654, 32655, 32656, 32657, 32658, 32659, 32660,  # WGS84 UTM 51N-60N
    32701, 32702, 32703, 32704, 32705, 32706, 32707, 32708, 32709, 32710,  # WGS84 UTM  1S-10S
    32711, 32712, 32713, 32714, 32715, 32716, 32717, 32718, 32719, 32720,  # WGS84 UTM 11S-20S
    32721, 32722, 32723, 32724, 32725, 32726, 32727, 32728, 32729, 32730,  # WGS84 UTM 21S-30S
    32731, 32732, 32733, 32734, 32735, 32736, 32737, 32738, 32739, 32740,  # WGS84 UTM 31S-40S
    32741, 32742, 32743, 32744, 32745, 32746, 32747, 32748, 32749, 32750,  # WGS84 UTM 41S-50S
    32751, 32752, 32753, 32754, 32755, 32756, 32757, 32758, 32759, 32760,  # WGS84 UTM 51S-60S
    0, # ImageCRS
)

class retrieve_czml(Component):
    """ Process to retrieve registered data (focused on Swarm data)
    """
    implements(ProcessInterface)

    identifier = "retrieve_czml"
    title = "Retrieve registered Swarm data based on collection, time intervall, [bbox] and resolution"
    metadata = {"test-metadata":"http://www.metadata.com/test-metadata"}
    profiles = ["test_profile"]

    inputs = [
        ("collection_ids", LiteralData('collection_ids', str, optional=False,
            abstract="String input for collection identifiers (semicolon separator)",
        )),
        ("begin_time", LiteralData('begin_time', dt.datetime, optional=False,
            abstract="Start of the time interval",
        )),
        ("end_time", LiteralData('end_time', dt.datetime, optional=False,
            abstract="End of the time interval",
        )),
        ("resolution", LiteralData('resolution', int, optional=True,
            default=20, abstract="Resolution attribute to define step size for returned elements",
            #TODO: think about how we want to implement this, maybe the process should check
            #      the result size and decide how to handle large amount of elements.
        )),
    ]


    outputs = [
        ("output",
            ComplexData('output',
                title="Requested subset of data",
                abstract="Process returns CZML file with coloured product measurement points of collections.",
                formats=FormatText('text/plain')
            )
        ),
    ]

    def execute(self, collection_ids, begin_time, end_time, resolution, **kwarg):
        outputs = {}

        collection_ids = collection_ids.split(",")

        collections = models.ProductCollection.objects.filter(identifier__in=collection_ids)
        
        sio = StringIO()

        range_type = collections[0].range_type

        # file-like text output
        tmp = CDTextBuffer()

        data = []
        data.append({"id":"document", "version":"1.0"})

        # TODO: assert that the range_type is equal for all collections

        for collection_id in collection_ids:
            coverages_qs = models.Product.objects.filter(collections__identifier=collection_id)
            coverages_qs = coverages_qs.filter(begin_time__lte=end_time)
            coverages_qs = coverages_qs.filter(end_time__gte=begin_time)

            for coverage in coverages_qs:
                #collection_id = models.ProductCollection.objects.filter(identifier__in=collection_id)
                cov_begin_time, cov_end_time = coverage.time_extent
                cov_cast = coverage.cast()
                t_res = get_total_seconds(cov_cast.resolution_time)
                low = max(0, int(get_total_seconds(begin_time - cov_begin_time) / t_res))
                high = min(cov_cast.size_x, int(math.ceil(get_total_seconds(end_time - cov_begin_time) / t_res)))
                self.handle(cov_cast, collection_id, range_type, low, high, resolution, begin_time, end_time, data)


        tmp.write(json.dumps(data))
        outputs['output'] = tmp

        return outputs


    def handle(self, coverage, collection_id, range_type, low, high, resolution, begin_time, end_time, data):
        # Open file
        filename = connect(coverage.data_items.all()[0])

        ds = pycdf.CDF(filename)
        output_data = OrderedDict()

        cs = matplotlib.cm.ScalarMappable(cmap="jet")
        cs.set_clim(30000,60000)

        # Read data
        for band in range_type:
            data = ds[band.identifier]
            output_data[band.identifier] = data[low:high:resolution]

        lons = output_data["Longitude"]
        lats = output_data["Latitude"]
        rads = output_data["Radius"]
        fs = output_data["F"]

        for lon, lat, r, f in zip (lons, lats, rads, fs):
            color = cs.to_rgba(f)
            id = str(uuid4())
            data.append({
                "id": id,
                "point": {
                  "pixelSize": 10, 
                  "show": True,
                  "color": {
                    "rgba": [int(v*256) for v in color]
                  }
                },
                "position": {
                  "cartographicDegrees": [lon,lat,r-6384000]
                }
            })


        
def translate(arr):

    try:
        if arr.ndim == 1:
            return "{%s}" % ";".join(map(str, arr))
    except:
        pass

    return arr
