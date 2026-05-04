from __future__ import annotations

from .caribbean_mls import scrape as scrape_caribbean_mls
from .cb_jamaica import scrape as scrape_cb_jamaica
from .century21_jm import scrape as scrape_century21_jm
from .golden_gates import scrape as scrape_golden_gates
from .millennium import scrape as scrape_millennium
from .realtor_com_intl import scrape as scrape_realtor_com_intl
from .xposure_manual import scrape as scrape_xposure_manual

ALL_SCRAPERS = [
    ("realtor_com_intl", scrape_realtor_com_intl),
    ("cb_jamaica", scrape_cb_jamaica),
    ("caribbean_mls", scrape_caribbean_mls),
    ("millennium", scrape_millennium),
    ("golden_gates", scrape_golden_gates),
    ("century21_jm", scrape_century21_jm),
    ("xposure", scrape_xposure_manual),
]
