from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    slug: str
    name: str
    lat: float
    lon: float
    radius_miles: float
    home_budget_usd: int
    land_budget_usd: int
    boost_keywords: tuple[str, ...]


REGIONS: tuple[Region, ...] = (
    Region(
        slug="upton",
        name="Upton Estate Golf & Country Club",
        lat=18.38427930703869,
        lon=-77.06401634785209,
        radius_miles=7.0,
        home_budget_usd=650_000,
        land_budget_usd=300_000,
        boost_keywords=("upton estate", "upton", "sandals golf", "sandals", "golf course", "country club"),
    ),
)


def by_slug(slug: str) -> Region | None:
    return next((r for r in REGIONS if r.slug == slug), None)
