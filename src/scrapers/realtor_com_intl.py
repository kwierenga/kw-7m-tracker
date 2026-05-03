"""realtor.com international Jamaica search results."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing

SOURCE = "realtor_com_intl"
BASE = "https://www.realtor.com"
URLS = [f"{BASE}/international/jm/"]


def scrape() -> list[RawListing]:
    out: list[RawListing] = []
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
                out.extend(_parse(r.text))
            except Exception:  # noqa: BLE001
                continue
    return out


def _parse(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    cards = soup.select(
        'div[data-testid="standard-listing-card"], '
        'div[data-testid="boost-listing-card-non-desktop"]'
    )
    for card in cards:
        a = card.find("a", href=re.compile(r"^/international/jm/"))
        if not a:
            ancestor = card.find_parent("a", href=re.compile(r"^/international/jm/"))
            if not ancestor:
                continue
            a = ancestor
        href = a["href"]
        url = href if href.startswith("http") else f"{BASE}{href}"
        m = re.search(r"-(\d+)/?$", href.rstrip("/"))
        source_id = m.group(1) if m else href

        addr_el = card.select_one(".address")
        address = addr_el.get_text(" ", strip=True) if addr_el else None

        usd_el = card.select_one(".displayConsumerPrice")
        jmd_el = card.select_one(".displayListingPrice")
        usd_text = usd_el.get_text(" ", strip=True) if usd_el else ""
        jmd_text = jmd_el.get_text(" ", strip=True) if jmd_el else ""
        price = usd_text or jmd_text or None

        ptype_el = card.select_one(".property-type")
        ptype = ptype_el.get_text(" ", strip=True) if ptype_el else ""

        feat_text = " ".join(
            f.get_text(" ", strip=True) for f in card.select(".features .feature-item")
        )

        title_parts = [p for p in (ptype, address) if p]
        title = " — ".join(title_parts) if title_parts else "(untitled)"

        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title,
                raw_price=price,
                raw_location=address,
                description=feat_text or None,
                fetched_at=fetched_at,
                listed_on_iso=None,
            )
        )
    return out
