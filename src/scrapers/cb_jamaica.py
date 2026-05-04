"""cbjamaica.com (Coldwell Banker Jamaica) - featured + recent listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ..photos import extract_first_img

SOURCE = "cb_jamaica"
BASE = "https://cbjamaica.com"
URLS = [
    f"{BASE}/featured-properties",
    f"{BASE}/recent-properties",
    f"{BASE}/",  # home page also has 9 listings — backup
]


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen_urls: set[str] = set()
    with cf.Session(impersonate="chrome131") as s:
        try:
            s.get(f"{BASE}/", allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for url in URLS:
            try:
                r = s.get(url, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    continue
                for raw in _parse(r.text):
                    if raw.url not in seen_urls:
                        seen_urls.add(raw.url)
                        out.append(raw)
            except Exception:  # noqa: BLE001
                continue
    return out


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    for card in soup.select("div.feature_listing_items, div.recent_listing_items"):
        a = card.find("a", href=re.compile(r"/property/"))
        if not a:
            continue
        url = a["href"]
        if not url.startswith("http"):
            url = BASE + ("" if url.startswith("/") else "/") + url
        m = re.search(r"MLS-([A-Za-z0-9]+)", url)
        source_id = m.group(1) if m else url.rstrip("/").split("/")[-1]

        price_el = card.select_one(".price_text")
        price = price_el.get_text(" ", strip=True) if price_el else None

        title_el = card.select_one(".prop_title")
        location = title_el.get_text(" ", strip=True) if title_el else None

        ptype_el = card.select_one(".prop_typetxt .inr_title")
        ptype = ptype_el.get_text(" ", strip=True) if ptype_el else ""

        title_parts = [p for p in (ptype, location) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        out.append(
            RawListing(
                source=SOURCE,
                source_id=str(source_id),
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
