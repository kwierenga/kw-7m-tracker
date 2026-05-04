"""millenniumpropertiessalesandservices.com - server-rendered featured listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import unquote

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing

SOURCE = "millennium"
BASE = "https://www.millenniumpropertiessalesandservices.com"
URLS = [f"{BASE}/", f"{BASE}/property-search?rent_sale=sale"]


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    with cf.Session(impersonate="chrome131") as s:
        for url in URLS:
            try:
                r = s.get(url, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    continue
                for raw in _parse(r.text):
                    if raw.url not in seen:
                        seen.add(raw.url)
                        out.append(raw)
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

        price_el = card.select_one(".price h4") or card.select_one(".property_listing_price h4")
        price = price_el.get_text(" ", strip=True) if price_el else None

        # Location is encoded in the URL slug — decode it
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
