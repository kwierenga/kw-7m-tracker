"""goldengatesrealtyja.com - server-rendered featured listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing

SOURCE = "golden_gates"
BASE = "https://www.goldengatesrealtyja.com"
URLS = [
    f"{BASE}/",
    f"{BASE}/property-search?rent_sale=sale",
]


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

        m = re.search(r"/(MLS-[A-Za-z0-9]+|GGR-[A-Za-z0-9]+)/?$", url)
        source_id = m.group(1) if m else url.rstrip("/").split("/")[-1]

        # Property type
        type_el = card.select_one(".bottom_texts .lefttext h3.title") or card.select_one("h3.title")
        ptype = type_el.get_text(" ", strip=True) if type_el else ""

        # For sale/rent badge
        badge_el = card.select_one(".badge_wraps .forsale_badge")
        transaction = badge_el.get_text(" ", strip=True) if badge_el else ""

        title_parts = [p for p in (ptype, transaction.lstrip(" ")) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        # Location (cleanest format of the three: "St. Ann, Laughlands")
        loc_el = card.select_one(".property_listing_content h3.prop_title") or card.select_one("h3.prop_title")
        location = loc_el.get_text(" ", strip=True) if loc_el else None

        # Price
        price_el = card.select_one(".bottom_texts .lefttext h4.price_text") or card.select_one("h4.price_text")
        price = price_el.get_text(" ", strip=True) if price_el else None

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=f"{title} — {location}" if location else title,
                raw_price=price,
                raw_location=location,
                description=None,
                fetched_at=fetched_at,
                listed_on_iso=None,
            )
        )
    return out
