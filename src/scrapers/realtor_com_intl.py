"""realtor.com international Jamaica search results."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from ..models import RawListing
from ..photos import extract_first_img
from ._throttle import Throttle, polite_get

SOURCE = "realtor_com_intl"
BASE = "https://www.realtor.com"
# Page-1 URL plus paginated p2..p25 (Jamaica search has 15+ pages of ~25
# listings each as of 2026-05). Cap is conservative; without pagination we
# only saw the rotating top-19, which fired false 'dropped off' alerts every
# time a listing was pushed off page 1 by newer ones.
PAGE_CAP = 25


def _build_urls() -> list[str]:
    urls = [f"{BASE}/international/jm/"]
    for page in range(2, PAGE_CAP + 1):
        urls.append(f"{BASE}/international/jm/p{page}/")
    return urls


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
        for i, url in enumerate(_build_urls()):
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
                # Page 1 may legitimately overlap with prior pages on the
                # bootstrap; only count empty pages on paginated entries.
                if i > 0 and new_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                else:
                    consecutive_empty = 0
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
                photo_url=extract_first_img(card, BASE),
            )
        )
    return out
