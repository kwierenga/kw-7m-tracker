"""millenniumpropertiessalesandservices.com - server-rendered listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import unquote

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing

SOURCE = "millennium"
BASE = "https://www.millenniumpropertiessalesandservices.com"


def _build_urls() -> list[str]:
    urls = [
        f"{BASE}/",
        f"{BASE}/property-search?rent_sale=sale",
    ]
    # Try common pagination conventions; break-on-empty handles whichever doesn't work.
    for page in range(2, 8):
        urls.append(f"{BASE}/property-search?rent_sale=sale&page={page}")
    return urls


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    consecutive_empty_paginated = 0
    with cf.Session(impersonate="chrome131") as s:
        try:
            s.get(f"{BASE}/", allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for url in _build_urls():
            is_paginated = "page=" in url
            try:
                r = s.get(url, allow_redirects=True, timeout=30)
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
    for card in soup.select("div.property_listing_items"):
        a = card.select_one(".property_listing_img a[href]") or card.find("a", href=re.compile(r"/property/"))
        if not a:
            continue
        url = a["href"]
        if not url.startswith("http"):
            url = BASE + ("" if url.startswith("/") else "/") + url

        m = re.search(r"MLS-([A-Za-z0-9]+)", url)
        source_id = m.group(1) if m else url.rstrip("/").split("/")[-1]

        title_el = card.select_one(".prop_type_mls_row h4") or card.select_one(".property_listing_content h4")
        title_text = title_el.get_text(" ", strip=True) if title_el else ""

        # Skip rentals — Klaas is buying, not renting
        if "rent" in title_text.lower() or "lease" in title_text.lower():
            continue

        price_el = card.select_one(".price h4") or card.select_one(".property_listing_price h4")
        price = price_el.get_text(" ", strip=True) if price_el else None

        location = None
        loc_match = re.search(r"/property/([^/]+)/MLS-", url)
        if loc_match:
            slug = unquote(loc_match.group(1))
            location = (
                slug.replace("-and-", " & ")
                .replace("-dot-", ".")
                .replace("+", " ")
                .replace("-", " ")
                .strip()
            )

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title_text or "(untitled)",
                raw_price=price,
                raw_location=location,
                description=None,
                fetched_at=fetched_at,
                listed_on_iso=None,
            )
        )
    return out
