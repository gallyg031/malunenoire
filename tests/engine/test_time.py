# -*- coding: utf-8 -*-
"""Entrée du temps (spec 07 §1 « Temps ») : offsets résolus par zoneinfo uniquement."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe

import astro


@pytest.mark.parametrize("args, offset_min", [
    ((1991, 3, 12, 4, 37, "Europe/Paris"), 60),
    ((1991, 7, 12, 4, 37, "Europe/Paris"), 120),
    ((1943, 6, 1, 12, 0, "Europe/Paris"), 120),   # heure allemande
    ((1991, 3, 12, 4, 37, "Asia/Tokyo"), 540),
    ((1991, 1, 12, 4, 37, "America/Montreal"), -300),
    ((1991, 7, 12, 4, 37, "America/Montreal"), -240),
])
def test_to_jd_offset(args, offset_min):
    jd, off = astro.to_jd(*args)
    assert round(off * 60) == offset_min
    # le jd correspond bien à l'instant UTC
    local = datetime(*args[:5], tzinfo=ZoneInfo(args[5]))
    ut = local.astimezone(ZoneInfo("UTC"))
    assert jd == pytest.approx(swe.julday(ut.year, ut.month, ut.day, ut.hour + ut.minute / 60), abs=1e-9)


def test_to_jd_tz_inconnu():
    with pytest.raises(Exception):
        astro.to_jd(1991, 3, 12, 4, 37, "Europe/Atlantide")
