from __future__ import annotations

from .realtor_jamaica import scrape as scrape_realtor_jamaica

ALL_SCRAPERS = [
    ("realtor_jamaica", scrape_realtor_jamaica),
]
