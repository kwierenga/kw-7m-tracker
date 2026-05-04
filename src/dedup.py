from __future__ import annotations

from .geo import haversine_miles
from .models import NormalizedListing


def _close_in_geo(a: NormalizedListing, b: NormalizedListing) -> bool:
    if a.lat is None or b.lat is None:
        return False
    return haversine_miles(a.lat, a.lon, b.lat, b.lon) * 1609.34 < 100  # ~100m


def _close_in_price(a: NormalizedListing, b: NormalizedListing) -> bool:
    if a.price_usd is None or b.price_usd is None:
        return False
    if a.price_usd == 0 or b.price_usd == 0:
        return False
    diff = abs(a.price_usd - b.price_usd) / max(a.price_usd, b.price_usd)
    return diff < 0.05


def _merge(a: NormalizedListing, b: NormalizedListing) -> NormalizedListing:
    """Merge b INTO a. a wins on most fields except: lower price, longer description, more sources/urls, earlier listed_on."""
    sources = list(dict.fromkeys(a.sources + b.sources))
    urls = list(dict.fromkeys(a.urls + b.urls))
    price = a.price_usd
    if b.price_usd is not None and (price is None or b.price_usd < price):
        price = b.price_usd
    desc = a.description if (a.description and len(a.description) >= len(b.description or "")) else b.description
    listed_on = min(filter(None, [a.listed_on_iso, b.listed_on_iso]), default=None)
    return NormalizedListing(
        stable_id=a.stable_id,
        sources=sources,
        urls=urls,
        title=a.title or b.title,
        description=desc,
        property_type=a.property_type if a.property_type != "unknown" else b.property_type,
        price_usd=price,
        price_original=a.price_original or b.price_original,
        price_currency=a.price_currency if a.price_currency != "unknown" else b.price_currency,
        lat=a.lat or b.lat,
        lon=a.lon or b.lon,
        location_text=a.location_text or b.location_text,
        location_confidence=a.location_confidence,
        matched_regions=list(dict.fromkeys(a.matched_regions + b.matched_regions)),
        keyword_boost=a.keyword_boost or b.keyword_boost,
        listed_on_iso=listed_on,
        photo_url=a.photo_url or b.photo_url,
    )


def dedup(listings: list[NormalizedListing]) -> list[NormalizedListing]:
    out: list[NormalizedListing] = []
    for L in listings:
        absorbed = False
        for i, existing in enumerate(out):
            if _close_in_geo(L, existing) and _close_in_price(L, existing):
                out[i] = _merge(existing, L)
                absorbed = True
                break
        if not absorbed:
            out.append(L)
    return out
