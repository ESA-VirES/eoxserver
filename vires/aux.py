

from django.conf import settings
from spacepy import pycdf
import numpy as np

from vires import jdutil


def _open_db(mode="r"):
    cdf = pycdf.CDF(settings.VIRES_AUX_DB_DST)
    if mode == "w":
        cdf.readonly(False)
    return cdf


def mjd2000_to_datetime(mjd):
    return jdutil.jd_to_datetime(mjd + 2451544.5)


def update_db(file_dst, file_kp):
    cdf_dst = pycdf.CDF(settings.VIRES_AUX_DB_DST)
    cdf_dst.readonly(False)
    cdf_dst["time"], cdf_dst["dst"], cdf_dst["est"], cdf_dst["ist"] = _parse_dst(file_dst)
    cdf_dst.close()


def _parse_dst(filename):
    def _parse_line(line):
        mjd, dst, est, ist, flag = line.strip().split()
        return mjd2000_to_datetime(float(mjd)), float(dst), float(est), float(ist)

    with open(filename) as f:
        arr = np.array(
            _parse_line(line) for line in f
        )

    return arr.T
