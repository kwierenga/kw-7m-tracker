"""sagicorproperties.com — Sagicor Property Services, server-rendered.

Same template family as Golden Gates / Millennium (.property_listing_items
cards), so card parsing is straightforward. We narrow the search by the
?parish=<name> filter and walk only the four parishes our regions live in
— island-wide there are ~7,000 sale listings, but only ~1,500 across St
Ann / Trelawny / Portland / Westmoreland.

The README's old guess of `sagicorpropertiesja.com` doesn't exist; the
working domain is `sagicorproperties.com`. The AWS WAF block listed in
the dropped-sources table is no longer present (impersonate=chrome131
gets through cleanly).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ..photos import extract_first_img
from ._throttle import Throttle, polite_get

SOURCE = "sagicor_props"
BASE = "https://www.sagicorproperties.com"

# Parish names as the site's filter expects them. Restricted to the four
# parishes our regions overlap.
RELEVANT_PARISHES: tuple[str, ...] = ("St. Ann", "Trelawny", "Portland", "Westmoreland")
PER_PAGE = 100
MAX_PAGES_PER_PARISH = 15  # 15*100 = 1500 per parish — well above current totals


def _build_urls() -> list[str]:
    urls = [f"{BASE}/"]
    for parish in RELEVANT_PARISHES:
        for page in range(1, MAX_PAGES_PER_PARISH + 1):
            urls.append(
                f"{BASE}/property-search?category=residential&rent_sale=sale"
                f"&parish={parish.replace(' ', '+')}&limit={PER_PAGE}&page={page}"
            )
    return urls


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    consecutive_empty_paginated = 0
    last_parish: str | None = None
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        try:
            polite_get(s, f"{BASE}/", throttle, allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for url in _build_urls():
            is_paginated = "page=" in url
            # Reset the empty-page counter when we move to a new parish so a
            # short parish (e.g. Portland, ~2 pages) doesn't break out of the
            # whole loop.
            parish_match = re.search(r"parish=([^&]+)", url)
            current_parish = parish_match.group(1) if parish_match else None
            if current_parish != last_parish:
                consecutive_empty_paginated = 0
                last_parish = current_parish
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    if is_paginated:
                        consecutive_empty_paginated += 1
                        if consecutive_empty_paginated >= 2:
                            # Skip rest of this parish's pages
                            continue
                    continue
                new_count = 0
                for raw in _parse(r.text):
                    if raw.url not in seen:
                        seen.add(raw.url)
                        out.append(raw)
                        new_count += 1
                if is_paginated and new_count == 0:
                    consecutive_empty_paginated += 1
                else:
                    consecutive_empty_paginated = 0
            except Exception:  # noqa: BLE001
                continue
    return out


_MLS_RE = re.compile(r"/(MLS-[A-Za-z0-9]+|SPSL-[A-Za-z0-9]+|SPSR-[A-Za-z0-9]+)/?$")


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    for card in soup.select("div.property_listing_items"):
        a = card.select_one(".property_listing_img a[href]") or card.find(
            "a", href=re.compile(r"/property/")
        )
        if not a:
            continue
        url = a.get("href") or ""
        if not url:
            continue
        if not url.startswith("http"):
            url = BASE + ("" if url.startswith("/") else "/") + url

        m = _MLS_RE.search(url)
        source_id = m.group(1) if m else url.rstrip("/").split("/")[-1]

        loc_el = card.select_one(".property_listing_content h3.prop_title") or card.select_one(
            "h3.prop_title"
        )
        location = loc_el.get_text(" ", strip=True) if loc_el else None

        # property type is sometimes in a (commented-out) prop_nature, fall
        # back to scraping it from the URL path which encodes it differently
        type_el = card.select_one("h3.prop_nature")
        ptype = type_el.get_text(" ", strip=True) if type_el else ""

        price_el = card.select_one("h4.price_text")
        price = re.sub(r"\s+", " ", price_el.get_text(" ", strip=True)) if price_el else None

        desc_el = card.select_one(".property_listing_content p")
        description = desc_el.get_text(" ", strip=True) if desc_el else None

        title_parts = [p for p in (ptype, location) if p]
        title = " — ".join(title_parts) if title_parts else (location or "(untitled)")

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
                photo_url=extract_first_img(card, BASE),
            )
        )
    return out
