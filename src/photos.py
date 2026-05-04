"""Photo URL extraction helper for scrapers."""
from __future__ import annotations

from urllib.parse import urljoin


def extract_first_img(card, base_url: str = "") -> str | None:
    """Best-effort: pull a usable img URL from a listing card.

    Tries data-src / data-lazy-src first (lazy-loaded images), then src.
    Skips data: URIs and obvious 1x1 trackers/placeholders.
    Resolves relative URLs against base_url if provided.
    """
    if card is None:
        return None
    img = card.select_one("img")
    if img is None:
        return None
    candidates = [
        img.get("data-src"),
        img.get("data-lazy-src"),
        img.get("data-original"),
        img.get("src"),
    ]
    for raw in candidates:
        if not raw or not isinstance(raw, str):
            continue
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("data:"):
            continue
        if any(p in raw.lower() for p in ("1x1.gif", "blank.gif", "spacer.gif", "placeholder")):
            continue
        if raw.startswith("//"):
            return f"https:{raw}"
        if raw.startswith("/") and base_url:
            return urljoin(base_url, raw)
        if raw.startswith("http"):
            return raw
        if base_url:
            return urljoin(base_url, raw)
        return raw
    return None
