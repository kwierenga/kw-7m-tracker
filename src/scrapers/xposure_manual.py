"""xposure manual-ingest: reads tokenized InteractiveLink URLs from data/xposure_urls.txt.

Klaas's realtor friend shares listings via InteractiveLink URLs that work
without auth. Paste them (one per line) into data/xposure_urls.txt and they'll
be ingested into the same dedup/diff pipeline as the public sources.

Format of data/xposure_urls.txt:
    # comments start with #
    https://jamaica.xposureapp.com/portal/jamaica/InteractiveLink?u=...&l=...&t=mls&h=...&pl=true
    https://jamaica.xposureapp.com/portal/jamaica/InteractiveLink?u=...&l=...&t=mls&h=...&pl=true
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ._throttle import Throttle, polite_get

SOURCE = "xposure"
URLS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "xposure_urls.txt"


def _load_urls() -> list[str]:
    if not URLS_FILE.exists():
        return []
    out = []
    for line in URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def scrape() -> list[RawListing]:
    urls = _load_urls()
    if not urls:
        return []
    out: list[RawListing] = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        for url in urls:
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    continue
                listing = _parse(r.text, url, fetched_at)
                if listing:
                    out.append(listing)
            except Exception:  # noqa: BLE001
                continue
    return out


def _parse(html: str, source_url: str, fetched_at: str) -> RawListing | None:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("div.listing-container")
    if not container:
        return None

    # Photo from og:image meta (most reliable for xposure)
    og = soup.select_one('meta[property="og:image"]')
    photo_url = og.get("content") if og else None
    if not photo_url:
        img = container.select_one("img")
        if img:
            photo_url = img.get("src")

    # MLS id from the listing-info table; fall back to URL param l=...
    mls_id: str | None = None
    for label_td in soup.select("td.listing-label"):
        txt = label_td.get_text(" ", strip=True).rstrip(":").lower()
        if txt.startswith("mls"):
            sib = label_td.find_next_sibling("td")
            if sib:
                mls_id = sib.get_text(" ", strip=True)
                break
    if not mls_id:
        m = re.search(r"[?&]l=(\d+)", source_url)
        mls_id = m.group(1) if m else source_url

    addr = container.select_one("span.listing-address")
    area = container.select_one("span.listing-area")
    subarea = container.select_one("span.listing-subarea")
    parts = [
        x.get_text(" ", strip=True)
        for x in (subarea, area)
        if x and x.get_text(strip=True)
    ]
    location = ", ".join(parts) if parts else (
        addr.get_text(" ", strip=True) if addr else None
    )

    price_el = container.select_one("a.listing-price, span.listing-price")
    price = price_el.get_text(" ", strip=True) if price_el else None

    map_el = container.select_one("a.map-location[data-latitude][data-longitude]")
    lat = lon = None
    if map_el:
        try:
            lat = float(map_el.get("data-latitude"))
            lon = float(map_el.get("data-longitude"))
        except (TypeError, ValueError):
            pass

    desc_el = container.select_one("p.long-description") or container.select_one(
        "p.brief-description"
    )
    description = desc_el.get_text(" ", strip=True) if desc_el else None

    status: str | None = None
    for label_td in soup.select("td.listing-label"):
        if label_td.get_text(strip=True).rstrip(":").lower() == "status":
            sib = label_td.find_next_sibling("td")
            if sib:
                status = sib.get_text(" ", strip=True)
                break

    title = addr.get_text(" ", strip=True) if addr else "(untitled)"
    if status:
        title = f"[{status}] {title}"

    if lat is not None and lon is not None:
        coord = f"({lat},{lon})"
        description = f"{description} {coord}".strip() if description else coord

    return RawListing(
        source=SOURCE,
        source_id=str(mls_id),
        url=source_url,
        title=title,
        raw_price=price,
        raw_location=location,
        description=description,
        fetched_at=fetched_at,
        listed_on_iso=None,
        photo_url=photo_url,
    )
