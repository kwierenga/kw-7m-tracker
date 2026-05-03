"""RealtorJamaica.com scraper.

STATUS: skeleton. Selectors are TODO until we inspect real HTML.

Run scripts/inspect_sites.py first to capture pages, then update SEARCH_URLS,
LISTING_CARD_SELECTOR, and the field-extraction code below.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from ..dates import parse_jamaica_date, to_iso
from ..models import RawListing

SOURCE = "realtor_jamaica"
BASE = "https://www.realtorjamaica.com"

# TODO: confirm these against actual site after inspection
SEARCH_URLS = [
    f"{BASE}/property/?parishes=st-ann",
    f"{BASE}/property/?parishes=st-mary",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def scrape(client: httpx.Client | None = None) -> list[RawListing]:
    own = client is None
    c = client or httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=20)
    out: list[RawListing] = []
    try:
        for url in SEARCH_URLS:
            try:
                r = c.get(url)
                if r.status_code != 200:
                    continue
                out.extend(_parse_results(r.text))
            except httpx.HTTPError:
                continue
    finally:
        if own:
            c.close()
    return out


def _parse_results(html: str) -> list[RawListing]:
    """TODO: rewrite once we know the real HTML.

    Heuristic placeholder: look for <a> elements whose href contains '/property/'
    and treat each unique one as a candidate listing card. Title from anchor text,
    price by scanning for $ in the surrounding container.
    """
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/property/"]'):
        href = a.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else f"{BASE}{href}"
        source_id = href.rstrip("/").rsplit("/", 1)[-1] or href
        title = (a.get_text(" ", strip=True) or "")[:200]
        # Walk up to a card-like container to find price/location text
        container = a
        for _ in range(3):
            if container.parent:
                container = container.parent
        block_text = container.get_text(" ", strip=True) if container else ""
        # TODO: once we know the site, replace block_text with the actual
        # "Listed on:" element from the listing page.
        listed_on = to_iso(parse_jamaica_date(block_text))
        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=url,
                title=title or block_text[:120],
                raw_price=_extract_price(block_text),
                raw_location=None,
                description=block_text[:500] or None,
                fetched_at=fetched_at,
                listed_on_iso=listed_on,
            )
        )
    return out


def _extract_price(text: str) -> str | None:
    import re
    m = re.search(r"(US\$|J\$|JA\$|\$)\s*[\d][\d,]*(?:\.\d+)?\s*(?:M|K|million|thousand)?", text, re.IGNORECASE)
    return m.group(0) if m else None
