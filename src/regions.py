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
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=("upton estate", "upton", "sandals golf", "sandals", "golf course", "country club"),
    ),
    Region(
        slug="duncans",
        name="Duncans (Trelawny)",
        lat=18.483023452239546,
        lon=-77.52819198637663,
        radius_miles=7.0,
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=("duncans", "duncan's bay", "silver sands", "decameron", "stewart castle", "rio bueno"),
    ),
    Region(
        slug="discovery_bay",
        name="Discovery Bay",
        lat=18.459496273787785,
        lon=-77.3961843877396,
        radius_miles=7.0,
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=("discovery bay", "puerto seco", "queens highway", "salt gut"),
    ),
    Region(
        slug="runaway_bay",
        name="Runaway Bay / Cardiff Hall",
        lat=18.456198953962264,
        lon=-77.33284133794203,
        radius_miles=7.0,
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=("runaway bay", "cardiff hall", "salem", "sandals", "golf course", "country club"),
    ),
    Region(
        slug="mammee_bay",
        name="Mammee Bay",
        lat=18.426862987548827,
        lon=-77.1645513756921,
        radius_miles=7.0,
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=("mammee bay", "mamee bay", "drax hall", "priory", "st. ann's bay", "saint ann's bay"),
    ),
    Region(
        slug="port_antonio",
        name="Port Antonio (Portland)",
        lat=18.170815018374324,
        lon=-76.41287621369821,
        radius_miles=7.0,
        home_budget_usd=800_000,
        land_budget_usd=350_000,
        boost_keywords=(
            "port antonio", "san san", "frenchmans cove", "frenchman's cove",
            "boston bay", "drapers", "fairy hill", "blue lagoon", "geejam",
        ),
    ),
)


def by_slug(slug: str) -> Region | None:
    return next((r for r in REGIONS if r.slug == slug), None)
