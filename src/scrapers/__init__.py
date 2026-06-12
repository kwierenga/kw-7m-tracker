from __future__ import annotations

from .caribbean_mls import scrape as scrape_caribbean_mls
from .cb_jamaica import scrape as scrape_cb_jamaica
from .century21_jm import scrape as scrape_century21_jm
from .golden_gates import scrape as scrape_golden_gates
from .keez import scrape as scrape_keez
from .millennium import scrape as scrape_millennium
from .realtor_com_intl import scrape as scrape_realtor_com_intl
from .remax_elite import scrape as scrape_remax_elite
from .sagicor_props import scrape as scrape_sagicor_props
from .xposure_manual import scrape as scrape_xposure_manual

ALL_SCRAPERS = [
    ("realtor_com_intl", scrape_realtor_com_intl),
    ("cb_jamaica", scrape_cb_jamaica),
    ("caribbean_mls", scrape_caribbean_mls),
    ("millennium", scrape_millennium),
    ("golden_gates", scrape_golden_gates),
    ("century21_jm", scrape_century21_jm),
    ("remax_elite", scrape_remax_elite),
    ("keez", scrape_keez),
    ("sagicor_props", scrape_sagicor_props),
    ("xposure", scrape_xposure_manual),
]

# Sources whose scrape captures the COMPLETE active set every run, so a listing
# vanishing from the feed (while its URL still resolves) is a trustworthy
# "removed from sale / likely sold" signal rather than scrape-window noise.
#
# Strict criterion — include a source only when BOTH hold:
#   1. pagination runs to exhaustion (not a page cap that the active set could
#      outgrow — a cap near the listing count makes still-active listings
#      silently fall off the tail and look 'sold'), and
#   2. the feed lists every active record (no server-side rotation).
#
# keez qualifies: its API paginates until next_page_url is null, with a 2000/
# parish ceiling against ~1k actual. realtor.com is explicitly excluded (it
# rotates a page-1 window). The other paginated sites have MAX_PAGES caps
# uncomfortably close to their counts (century21 ~177/180) — add them here only
# after confirming the cap comfortably exceeds the live count.
COMPLETE_COVERAGE_SOURCES = frozenset({"keez"})
