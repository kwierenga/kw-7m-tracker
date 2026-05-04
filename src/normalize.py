from __future__ import annotations

import re

from .fx import parse_price
from .geo import lookup_centroid, haversine_miles
from .models import NormalizedListing, RawListing
from .regions import REGIONS, Region

LAND_HINTS = ("land", "lot", "acres", "acreage", "vacant", "plot")
HOME_HINTS = ("house", "home", "villa", "condo", "apartment", "townhouse", "bedroom", "bath")


def _infer_type(text: str) -> str:
    t = text.lower()
    has_land = any(h in t for h in LAND_HINTS)
    has_home = any(h in t for h in HOME_HINTS)
    if has_land and not has_home:
        return "land"
    if has_home:
        return "home"
    return "unknown"


def _keyword_boost(region: Region, text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in region.boost_keywords)


_LATLON_RE = re.compile(r"(-?\d{1,2}\.\d{3,})\s*[,/]\s*(-?\d{1,3}\.\d{3,})")


def _try_extract_latlon(text: str) -> tuple[float, float] | None:
    m = _LATLON_RE.search(text)
    if not m:
        return None
    try:
        lat, lon = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def normalize_one(raw: RawListing) -> NormalizedListing:
    haystack = " ".join(filter(None, [raw.title, raw.raw_location, raw.description]))
    price_usd, currency = parse_price(raw.raw_price or "")
    ptype = _infer_type(haystack)

    lat = lon = None
    confidence = "none"
    coords = _try_extract_latlon(haystack)
    if coords:
        lat, lon = coords
        confidence = "exact"
    else:
        centroid = lookup_centroid(haystack) if haystack else None
        if centroid:
            lat, lon = centroid
            confidence = "approximate"

    matched: list[str] = []
    boosted = False
    for region in REGIONS:
        kb = _keyword_boost(region, haystack)
        if kb:
            boosted = True
        in_geo = False
        if lat is not None and lon is not None:
            d = haversine_miles(lat, lon, region.lat, region.lon)
            in_geo = d <= region.radius_miles
        if not in_geo and confidence == "none" and kb:
            confidence = "inferred"
            in_geo = True
        if in_geo:
            cap = region.land_budget_usd if ptype == "land" else region.home_budget_usd
            if price_usd is None or price_usd <= cap:
                matched.append(region.slug)

    return NormalizedListing(
        stable_id=raw.stable_id,
        sources=[raw.source],
        urls=[raw.url],
        title=raw.title or "(untitled)",
        description=raw.description,
        property_type=ptype,  # type: ignore[arg-type]
        price_usd=price_usd,
        price_original=raw.raw_price,
        price_currency=currency,  # type: ignore[arg-type]
        lat=lat,
        lon=lon,
        location_text=raw.raw_location,
        location_confidence=confidence,  # type: ignore[arg-type]
        matched_regions=matched,
        keyword_boost=boosted,
        listed_on_iso=raw.listed_on_iso,
    )


RENT_PHRASES = (
    " for rent",
    "for-rent",
    " for lease",
    "rental property",
    "/month",
    " per month",
    " pcm",
    "monthly rent",
)


def _looks_like_rental(raw: RawListing) -> bool:
    text = " ".join(filter(None, [raw.title, raw.raw_location, raw.description, raw.raw_price])).lower()
    return any(p in text for p in RENT_PHRASES)


def normalize_all(raws: list[RawListing]) -> list[NormalizedListing]:
    return [normalize_one(r) for r in raws if not _looks_like_rental(r)]
