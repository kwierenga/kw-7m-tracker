"""century21jm.com - Century 21 Jamaica listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ..photos import extract_first_img
from ._throttle import Throttle, polite_get

SOURCE = "century21_jm"
BASE = "https://century21jm.com"


def _build_urls() -> list[str]:
    urls = [f"{BASE}/"]
    # The IDX search URL is a full template with placeholder segments for
    # every unfilled filter. The shorter form (just sale/page/N) returns 404.
    # Pull residential+commercial together so land/lots are included.
    base_search = (
        "/search/residential-commercial/residential-commercial/rent-sale/sale"
        "/parish/parish/town/town/property-type/property-type"
        "/currency/currency/id-search/id-search/sqft_total/sqft_total"
        "/bed/bed/bath/bath/search/search/from/from/to/to"
    )
    for page in range(1, 16):
        urls.append(f"{BASE}{base_search}/page/{page}/limit/12/range/H")
    return urls


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    consecutive_empty_paginated = 0
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        try:
            polite_get(s, f"{BASE}/", throttle, allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for url in _build_urls():
            is_paginated = "/page/" in url
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    if is_paginated:
                        consecutive_empty_paginated += 1
                        if consecutive_empty_paginated >= 2:
                            break
                    continue
                new_count = 0
                for raw in _parse(r.text):
                    if raw.url not in seen:
                        seen.add(raw.url)
                        out.append(raw)
                        new_count += 1
                if is_paginated and new_count == 0:
                    consecutive_empty_paginated += 1
                    if consecutive_empty_paginated >= 2:
                        break
                else:
                    consecutive_empty_paginated = 0
            except Exception:  # noqa: BLE001
                continue
    return out


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    for card in soup.select("div.card.f-h-prop-bx, div.f-h-prop-bx"):
        mls = card.get("data-mls")
        a = card.select_one("a.link-absolute[href]") or card.find("a", href=re.compile(r"/property/"))
        if not a:
            continue
        url = a["href"]
        if not url.startswith("http"):
            url = BASE + ("" if url.startswith("/") else "/") + url
        source_id = str(mls) if mls else url.rstrip("/").split("/")[-1]

        trans_el = card.select_one(".card-top ul li:first-child a")
        trans_text = trans_el.get_text(" ", strip=True).lower() if trans_el else ""
        if "rent" in trans_text or "lease" in trans_text:
            continue

        type_el = card.select_one(".card-top ul li:first-child strong")
        ptype = type_el.get_text(" ", strip=True) if type_el else ""

        loc_el = card.select_one(".card-top ul li:nth-child(2) a") or card.select_one(
            ".card-top ul li:nth-child(2)"
        )
        location = loc_el.get_text(" ", strip=True) if loc_el else None

        price_lis = card.select(".info_details li")
        price = price_lis[-1].get_text(" ", strip=True) if price_lis else None

        title_parts = [p for p in (ptype, location) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title,
                raw_price=price,
                raw_location=location,
                description=None,
                fetched_at=fetched_at,
                listed_on_iso=None,
                photo_url=extract_first_img(card, BASE),
            )
        )
    return out
