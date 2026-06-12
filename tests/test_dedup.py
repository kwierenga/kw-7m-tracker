"""Tests for src/dedup.py — cross-source merging.

The key correctness property: listings only merge on geography when BOTH have
EXACT coordinates. Approximate (town-centroid) coords must never drive a merge,
or distinct same-town listings collapse and a real for-sale listing disappears.
"""
from __future__ import annotations

import unittest

from src.dedup import dedup
from src.models import NormalizedListing


def _listing(
    sid: str,
    *,
    lat: float | None,
    lon: float | None,
    confidence: str,
    price_usd: int | None = 300_000,
    source: str = "src",
    status: str | None = None,
) -> NormalizedListing:
    return NormalizedListing(
        stable_id=sid,
        sources=[source],
        urls=[f"https://example.com/{sid}"],
        title=f"Home {sid}",
        description=None,
        property_type="home",
        price_usd=price_usd,
        price_original=f"${price_usd:,}" if price_usd else None,
        price_currency="USD",
        lat=lat,
        lon=lon,
        location_text="Runaway Bay",
        location_confidence=confidence,  # type: ignore[arg-type]
        matched_regions=["runaway_bay"],
        status=status,
        canonical_id=sid,
        contributing_source_ids=[(source, sid)],
    )


class DedupGeoConfidenceTests(unittest.TestCase):
    def test_same_centroid_does_not_merge(self):
        # Two distinct listings at the identical town centroid + same price.
        # Under the old rule these collapsed; they must now stay separate.
        a = _listing("A", lat=18.46, lon=-77.33, confidence="approximate")
        b = _listing("B", lat=18.46, lon=-77.33, confidence="approximate")
        out, reassign = dedup([a, b])
        self.assertEqual(len(out), 2)
        self.assertEqual(reassign, [])

    def test_both_exact_and_close_merges(self):
        a = _listing("A", lat=18.4600, lon=-77.3300, confidence="exact", source="keez")
        b = _listing("B", lat=18.4600, lon=-77.3301, confidence="exact", source="remax_elite")
        out, _ = dedup([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(set(out[0].sources), {"keez", "remax_elite"})

    def test_exact_but_far_apart_does_not_merge(self):
        a = _listing("A", lat=18.46, lon=-77.33, confidence="exact")
        b = _listing("B", lat=18.50, lon=-77.40, confidence="exact")  # ~8km away
        out, _ = dedup([a, b])
        self.assertEqual(len(out), 2)

    def test_one_exact_one_approximate_does_not_merge(self):
        a = _listing("A", lat=18.46, lon=-77.33, confidence="exact")
        b = _listing("B", lat=18.46, lon=-77.33, confidence="approximate")
        out, _ = dedup([a, b])
        self.assertEqual(len(out), 2)

    def test_exact_close_but_different_price_does_not_merge(self):
        a = _listing("A", lat=18.46, lon=-77.33, confidence="exact", price_usd=300_000)
        b = _listing("B", lat=18.46, lon=-77.33, confidence="exact", price_usd=500_000)
        out, _ = dedup([a, b])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
