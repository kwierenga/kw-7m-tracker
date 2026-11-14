"""remax-elite.com.jm - RE/MAX Elite Jamaica sale listings.

The site's default search lists its ~1,100 sale listings most-expensive
first and answers 403 past page ~30, so a flat walk stopped around US$1M
and never reached a listing under the budget caps (no in-region hit between
2026-07-01 and 2026-11-13). It also offers a proximity search —
?lattitude=&longitude= — returning listings within roughly 10 km of a
point: checked 2026-11-13 against the coordinates on 59 detail pages, the
farthest was 6.1 miles out. So each region's centre is walked with that
search, cheapest first (range=L), stopping at the first page whose cheapest
card is over the region's home budget. Cards only name a district and
parish, so each result carries the region it was found near as a hint
(RawListing.region_hints) and normalize trusts that over a centroid.

Nearly every ID is MLS-... — the Realtors Association feed that the WAF-blocked
golden_gates / sagicor / century21 sites mirror — so this walk recovers most
of what those blocks hide.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..fx import parse_price
from ..models import RawListing
from ..regions import REGIONS, Region
from ..status import normalize_status
from ._throttle import Throttle, polite_get

SOURCE = "remax_elite"
BASE = "https://remax-elite.com.jm"
PER_PAGE = 100  # the site honours limit=100 (its form default is 18)
# 1,500 cards per centre. The busiest centre (Upton) had ~600 under budget
# in 2026-11; the budget stop below normally ends a walk after 5-7 pages.
MAX_PAGES_PER_REGION = 15


def _search_url(region: Region, page: int) -> str:
    return f"{BASE}/property-search?" + urlencode({
        "rent_sale": "sale",
        "lattitude": f"{region.lat:.6f}",  # sic: the site's own parameter name
        "longitude": f"{region.lon:.6f}",
        "range": "L",  # Low - High
        "limit": PER_PAGE,
        "page": page,
    })


def _cheapest_usd(raws: list[RawListing]) -> float:
    prices = [p for p, _ in (parse_price(r.raw_price or "") for r in raws) if p is not None]
    return min(prices) if prices else 0.0


def scrape() -> list[RawListing]:
    out: dict[str, RawListing] = {}  # url -> listing; hints merge when regions overlap
    saw_200 = False
    last_status: int | None = None
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        try:
            polite_get(s, f"{BASE}/", throttle, allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for region in REGIONS:
            for page in range(1, MAX_PAGES_PER_REGION + 1):
                try:
                    r = polite_get(s, _search_url(region, page), throttle, allow_redirects=True, timeout=30)
                except Exception:  # noqa: BLE001
                    break
                last_status = r.status_code
                if r.status_code != 200:
                    break  # past the last page the site answers 403
                saw_200 = True
                raws = _parse(r.text)
                if not raws:
                    break
                for raw in raws:
                    kept = out.get(raw.url)
                    if kept is None:
                        raw.region_hints.append(region.slug)
                        out[raw.url] = raw
                    elif region.slug not in kept.region_hints:
                        kept.region_hints.append(region.slug)
                # Ascending by price: once a page's cheapest card is over the
                # region's larger (home) budget, nothing further can match.
                if _cheapest_usd(raws) > region.home_budget_usd:
                    break
    # A fully-blocked source must raise (-> recorded as failed) rather than
    # return an empty list that masquerades as a clean 0.
    if not saw_200:
        raise RuntimeError(f"{SOURCE}: no successful response (last status {last_status})")
    return list(out.values())


_BG_RE = re.compile(r"background-image\s*:\s*url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)
_ID_RE = re.compile(r"/(MLS-[A-Za-z0-9]+|RME-[A-Za-z0-9]+)/?$")


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    for card in soup.find_all(class_="propertysearch_pb"):
        # The badge_wrap carries both transaction ("Sale"/"Rent") and
        # availability ("Under Offer"/"Under Contract"/"Sold") labels — ~13% of
        # cards are under offer/contract. Skip rent/lease, capture the rest as
        # canonical status.
        badge_wrap = card.select_one(".badge_wrap")
        badge_text = badge_wrap.get_text(" ", strip=True) if badge_wrap else ""
        if "rent" in badge_text.lower() or "lease" in badge_text.lower():
            continue
        status = normalize_status(badge_text)

        a = card.select_one("a.link_absolute_internal[href]") or card.find(
            "a", href=re.compile(r"/property/")
        )
        if not a:
            continue
        url = a["href"]
        if not url.startswith("http"):
            url = BASE + ("" if url.startswith("/") else "/") + url

        acronym = card.select_one("input.acronym_id")
        if acronym and acronym.get("value"):
            source_id = str(acronym["value"]).strip()
        else:
            m = _ID_RE.search(url)
            source_id = m.group(1) if m else url.rstrip("/").split("/")[-1]

        loc_el = card.select_one(".box-collectionHomeDetails h5")
        location = loc_el.get_text(" ", strip=True) if loc_el else None

        price_el = card.select_one(".box-collectionHomeDetails p")
        price = price_el.get_text(" ", strip=True) if price_el else None

        ptype_el = card.find("h4")
        ptype = ptype_el.get_text(" ", strip=True) if ptype_el else ""

        desc_el = card.select_one("p.img-collection_para")
        description = desc_el.get_text(" ", strip=True) if desc_el else None

        title_parts = [p for p in (ptype, location) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        photo_url: str | None = None
        fig = card.select_one("figure.img-collectionHome")
        if fig and fig.get("style"):
            m = _BG_RE.search(fig["style"])
            if m:
                photo_url = m.group(1).strip()

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title,
                raw_price=price,
                raw_location=location,
                description=description,
                fetched_at=fetched_at,
                listed_on_iso=None,
                photo_url=photo_url,
                status=status,
            )
        )
    return out
