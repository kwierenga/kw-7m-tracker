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


def _pick_canonical(a: NormalizedListing, b: NormalizedListing) -> tuple[str | None, str | None]:
    """Choose which canonical_id survives a merge. Returns (winner, loser)
    where loser may be None when only one side had a canonical.
    Heuristic: prefer the lexicographically lower one when both are present
    (deterministic, stable). When only one side has a canonical, use it."""
    if a.canonical_id and b.canonical_id:
        if a.canonical_id == b.canonical_id:
            return a.canonical_id, None
        if a.canonical_id < b.canonical_id:
            return a.canonical_id, b.canonical_id
        return b.canonical_id, a.canonical_id
    return a.canonical_id or b.canonical_id, None


def _merge(a: NormalizedListing, b: NormalizedListing) -> tuple[NormalizedListing, str | None]:
    """Merge b INTO a. Returns (merged, displaced_canonical_id) — the second
    is set when a previously-distinct canonical_id needs to be reassigned
    in the aliases table. a wins on most fields except: lower price, longer
    description, more sources/urls, earlier listed_on."""
    sources = list(dict.fromkeys(a.sources + b.sources))
    urls = list(dict.fromkeys(a.urls + b.urls))
    price = a.price_usd
    if b.price_usd is not None and (price is None or b.price_usd < price):
        price = b.price_usd
    desc = a.description if (a.description and len(a.description) >= len(b.description or "")) else b.description
    listed_on = min(filter(None, [a.listed_on_iso, b.listed_on_iso]), default=None)
    contrib = list(dict.fromkeys(a.contributing_source_ids + b.contributing_source_ids))
    winner_canon, loser_canon = _pick_canonical(a, b)
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
        canonical_id=winner_canon,
        contributing_source_ids=contrib,
    ), loser_canon


def dedup(
    listings: list[NormalizedListing],
) -> tuple[list[NormalizedListing], list[tuple[str, str]]]:
    """Returns (deduped, alias_reassignments) where each reassignment is
    (loser_canonical_id, winner_canonical_id) — caller must replay these
    against the aliases table so future runs resolve consistently."""
    out: list[NormalizedListing] = []
    reassignments: list[tuple[str, str]] = []
    for L in listings:
        absorbed = False
        for i, existing in enumerate(out):
            if _close_in_geo(L, existing) and _close_in_price(L, existing):
                merged, loser = _merge(existing, L)
                out[i] = merged
                if loser and merged.canonical_id and loser != merged.canonical_id:
                    reassignments.append((loser, merged.canonical_id))
                absorbed = True
                break
        if not absorbed:
            out.append(L)
    return out, reassignments
