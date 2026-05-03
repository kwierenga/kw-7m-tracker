from __future__ import annotations

import math

EARTH_RADIUS_MI = 3958.7613


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


PARISH_CENTROIDS: dict[str, tuple[float, float]] = {
    "kingston": (17.9712, -76.7928),
    "st andrew": (18.0179, -76.7989),
    "st thomas": (17.9229, -76.3486),
    "portland": (18.1739, -76.4542),
    "st mary": (18.3678, -76.9622),
    "st ann": (18.4319, -77.2018),
    "trelawny": (18.4502, -77.6393),
    "st james": (18.4762, -77.8939),
    "hanover": (18.4144, -78.1331),
    "westmoreland": (18.2997, -78.1336),
    "st elizabeth": (18.0500, -77.7000),
    "manchester": (18.0458, -77.5079),
    "clarendon": (17.8669, -77.2400),
    "st catherine": (17.9911, -77.0049),
}


TOWN_CENTROIDS: dict[str, tuple[float, float]] = {
    "ocho rios": (18.4070, -77.1030),
    "upton": (18.3843, -77.0640),
    "discovery bay": (18.4690, -77.4070),
    "runaway bay": (18.4567, -77.3239),
    "st ann's bay": (18.4346, -77.2018),
    "oracabessa": (18.4061, -76.9472),
    "port maria": (18.3678, -76.8945),
    "browns town": (18.3833, -77.3667),
    "moneague": (18.2730, -77.0930),
    "fern gully": (18.3739, -77.1019),
    "tower isle": (18.4097, -76.9547),
    "boscobel": (18.4083, -76.9667),
}


def lookup_centroid(text: str) -> tuple[float, float] | None:
    """Best-effort: try town first (more specific), fall back to parish."""
    t = text.lower()
    for name, coords in TOWN_CENTROIDS.items():
        if name in t:
            return coords
    for name, coords in PARISH_CENTROIDS.items():
        if name in t:
            return coords
    return None
