from __future__ import annotations

from .caribbean_mls import scrape as scrape_caribbean_mls
from .cb_jamaica import scrape as scrape_cb_jamaica
from .realtor_com_intl import scrape as scrape_realtor_com_intl
from .xposure_manual import scrape as scrape_xposure_manual

ALL_SCRAPERS = [
    ("realtor_com_intl", scrape_realtor_com_intl),
    ("cb_jamaica", scrape_cb_jamaica),
    ("caribbean_mls", scrape_caribbean_mls),
    ("xposure", scrape_xposure_manual),
]
