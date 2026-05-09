"""getkeez.com — Laravel-paginated JSON API.

Unlike the HTML scrapers, this one talks to the site's public API directly:
GET /api/properties?rent_sale=sale&state=<code>&per_page=100. Each page is
a JSON envelope { current_page, last_page, data: [...] } with structured
records — lat/lon, photos, description, dates — so no soup parsing.

We only walk the four parishes that overlap our regions (St. Ann, Trelawny,
Portland, Westmoreland) — the full set is ~3,900 sale listings island-wide,
but most are in Kingston/St. Catherine which we never match.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from curl_cffi import requests as cf

from ..models import RawListing
from ._throttle import Throttle, polite_get

SOURCE = "keez"
BASE = "https://www.getkeez.com"

# State codes for the parishes our regions live in. Discovered by walking a
# few API pages and bucketing address.state values; see geo.PARISH_CENTROIDS
# for the matching English parish names.
RELEVANT_STATES: tuple[str, ...] = ("AN", "TR", "PO", "WE")
PER_PAGE = 100
MAX_PAGES_PER_STATE = 20  # 20*100 caps each parish at 2000 listings — far above current totals


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    throttle = Throttle()
    fetched_at = datetime.now(timezone.utc).isoformat()
    with cf.Session(impersonate="chrome131") as s:
        for code in RELEVANT_STATES:
            for page in range(1, MAX_PAGES_PER_STATE + 1):
                url = f"{BASE}/api/properties?rent_sale=sale&state={code}&per_page={PER_PAGE}&page={page}"
                try:
                    r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                    if r.status_code != 200:
                        break
                    payload = r.json()
                except Exception:  # noqa: BLE001
                    break
                items = payload.get("data") or []
                if not items:
                    break
                for raw in _parse_items(items, fetched_at):
                    if raw.url not in seen:
                        seen.add(raw.url)
                        out.append(raw)
                # Laravel paginator marks end of run with next_page_url=null
                if not payload.get("next_page_url"):
                    break
    return out


def _parse(text: str) -> list[RawListing]:
    """Test seam: parse one page of JSON (string) into RawListings."""
    payload = json.loads(text)
    items = payload.get("data") or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    return _parse_items(items, fetched_at)


def _parse_items(items: list[dict], fetched_at: str) -> list[RawListing]:
    out: list[RawListing] = []
    for item in items:
        if (item.get("rent_sale") or "").lower() != "sale":
            continue
        url = item.get("url")
        ident = item.get("id")
        if not url or ident is None:
            continue

        ptype = item.get("property_type_label") or item.get("property_type") or ""
        addr = item.get("address") or {}
        city = addr.get("city") or ""
        parish = addr.get("state_name") or ""
        street1 = addr.get("street1") or ""
        location_parts = [p for p in (street1, city, parish) if p]
        # de-dupe consecutive duplicates ("Negril, Negril, Westmoreland" → "Negril, Westmoreland")
        deduped: list[str] = []
        for p in location_parts:
            if not deduped or deduped[-1].lower() != p.lower():
                deduped.append(p)
        location = ", ".join(deduped) or None

        lat = addr.get("latitude")
        lon = addr.get("longitude")
        # Embed coords in the description so the existing _LATLON_RE in
        # normalize.py can pick them up — gives every keez listing
        # location_confidence='exact' instead of parish-level approximate.
        desc_parts: list[str] = []
        if item.get("description"):
            desc_parts.append(str(item["description"]).strip())
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            desc_parts.append(f"[coords: {lat}, {lon}]")
        description = "\n\n".join(desc_parts) if desc_parts else None

        currency = (item.get("currency") or "").upper()
        price_val = item.get("price_current")
        if isinstance(price_val, (int, float)) and price_val > 0 and currency:
            raw_price = f"{currency} ${int(price_val):,}"
        else:
            raw_price = None

        title_parts = [p for p in (ptype, location) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        photos = item.get("photos") or []
        photo_url = None
        if photos and isinstance(photos, list):
            first = photos[0] or {}
            photo_url = first.get("medium") or first.get("large") or first.get("url")

        listed_on_iso = _to_iso(item.get("date_listed"))

        out.append(
            RawListing(
                source=SOURCE,
                source_id=str(ident),
                url=url,
                title=title,
                raw_price=raw_price,
                raw_location=location,
                description=description,
                fetched_at=fetched_at,
                listed_on_iso=listed_on_iso,
                photo_url=photo_url,
            )
        )
    return out


def _to_iso(value) -> str | None:
    """API returns 'YYYY-MM-DD HH:MM:SS' (no timezone). Treat as UTC."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()
