from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PropertyType = Literal["home", "land", "unknown"]
Currency = Literal["USD", "JMD", "unknown"]


@dataclass
class RawListing:
    """Whatever a scraper produces. Minimal contract."""

    source: str
    source_id: str
    url: str
    title: str
    raw_price: str | None
    raw_location: str | None
    description: str | None
    fetched_at: str
    listed_on_iso: str | None = None  # listing's own publication date if exposed by site

    @property
    def stable_id(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass
class NormalizedListing:
    stable_id: str
    sources: list[str]
    urls: list[str]
    title: str
    description: str | None
    property_type: PropertyType
    price_usd: int | None
    price_original: str | None
    price_currency: Currency
    lat: float | None
    lon: float | None
    location_text: str | None
    location_confidence: Literal["exact", "approximate", "inferred", "none"]
    matched_regions: list[str] = field(default_factory=list)
    keyword_boost: bool = False
    listed_on_iso: str | None = None
    first_seen_iso: str | None = None
    last_seen_iso: str | None = None
