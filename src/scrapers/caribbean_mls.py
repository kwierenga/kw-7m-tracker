"""caribbeanrealestatemls.com - Next.js, listings live in __NEXT_DATA__ JSON."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ._throttle import Throttle, polite_get

SOURCE = "caribbean_mls"
BASE = "https://caribbeanrealestatemls.com"
URLS = [f"{BASE}/destinations/jamaica/"]


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        for url in URLS:
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    continue
                out.extend(_parse(r.text))
            except Exception:  # noqa: BLE001
                continue
    return out


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return []
    page_props = data.get("props", {}).get("pageProps", {})
    page_data = page_props.get("pageData", {}) or {}
    properties = (
        page_data.get("properties")
        or page_props.get("properties")
        or page_props.get("results")
        or page_props.get("items")
        or []
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        source_id = str(prop.get("id") or prop.get("uuid") or prop.get("slug") or "")
        if not source_id:
            continue
        public_url = prop.get("public_url") or prop.get("url") or ""
        url = public_url if public_url.startswith("http") else BASE + public_url

        title = prop.get("title") or prop.get("name") or prop.get("type") or "(untitled)"
        ptype = prop.get("type") or prop.get("property_type") or ""
        if ptype and ptype.lower() not in title.lower():
            title = f"{ptype} — {title}"

        price = prop.get("price")
        currency = prop.get("currency") or "USD"
        raw_price: str | None = None
        if isinstance(price, (int, float)) and price:
            sym = "US$" if str(currency).upper() == "USD" else (
                "J$" if str(currency).upper() == "JMD" else f"{currency} "
            )
            raw_price = f"{sym} {int(price):,}"

        listed_on = (
            prop.get("listed_at")
            or prop.get("created")
            or prop.get("created_at")
            or prop.get("published_at")
        )

        location_text = (
            prop.get("location")
            or prop.get("city")
            or prop.get("address")
            or prop.get("region")
        )
        if not location_text and public_url:
            m = re.search(r"/real-estate/([^/]+)/", public_url)
            if m:
                location_text = m.group(1).replace("-", " ").title()

        lat = prop.get("latitude") or prop.get("lat")
        lon = prop.get("longitude") or prop.get("lng") or prop.get("lon")
        description = prop.get("description")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            tag_str = f"({lat},{lon})"
            description = f"{description} {tag_str}".strip() if description else tag_str

        # Photo from preview object (per agent inspection: small/medium/large keys)
        preview = prop.get("preview") or {}
        photo_path = (
            preview.get("medium")
            or preview.get("large")
            or preview.get("small")
            if isinstance(preview, dict)
            else None
        )
        photo_url = None
        if isinstance(photo_path, str) and photo_path:
            if photo_path.startswith("http"):
                photo_url = photo_path
            else:
                photo_url = BASE + ("" if photo_path.startswith("/") else "/") + photo_path

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title,
                raw_price=raw_price,
                raw_location=location_text if isinstance(location_text, str) else None,
                description=description if isinstance(description, str) else None,
                fetched_at=fetched_at,
                listed_on_iso=listed_on if isinstance(listed_on, str) else None,
                photo_url=photo_url,
            )
        )
    return out
