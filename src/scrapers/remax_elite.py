"""remax-elite.com.jm - RE/MAX Elite Jamaica sale listings."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ..status import normalize_status
from ._throttle import Throttle, polite_get

SOURCE = "remax_elite"
BASE = "https://remax-elite.com.jm"
PAGE_LIMIT = 18  # site default; matches their ?limit=18

# Site exposes hundreds of pages of sale listings. Stop early if pages run out.
# Cap conservatively so a one-shot scrape stays bounded.
MAX_PAGES = 60


def _build_urls() -> list[str]:
    return [
        f"{BASE}/property-search?rent_sale=sale&page={p}&limit={PAGE_LIMIT}"
        for p in range(1, MAX_PAGES + 1)
    ]


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    consecutive_empty = 0
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        try:
            polite_get(s, f"{BASE}/", throttle, allow_redirects=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        for url in _build_urls():
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                    continue
                new_count = 0
                for raw in _parse(r.text):
                    if raw.url not in seen:
                        seen.add(raw.url)
                        out.append(raw)
                        new_count += 1
                if new_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                else:
                    consecutive_empty = 0
            except Exception:  # noqa: BLE001
                continue
    return out


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
