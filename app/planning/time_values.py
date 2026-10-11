"""Minute arithmetic shared by plan phases; 24:00 is a valid boundary."""

import math


def minute(value):
    h, m = map(int, value.split(":"))
    return h * 60 + m


def round_up(m, step=5):
    return int(math.ceil(m / step) * step)


def clock(m):
    return f"{m // 60:02d}:{m % 60:02d}"
