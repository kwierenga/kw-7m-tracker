import unittest

from src.models import RawListing
from src.normalize import normalize_one


def _raw(location: str, price: str, hints: list[str] | None = None, description: str | None = None) -> RawListing:
    return RawListing(
        source="t", source_id="1", url="https://x/1", title=f"House — {location}",
        raw_price=price, raw_location=location, description=description,
        fetched_at="2026-11-13T00:00:00+00:00", region_hints=list(hints or []),
    )


class RegionHintTests(unittest.TestCase):
    def test_hint_overrides_parish_centroid(self) -> None:
        # "St. Ann" alone resolves to the parish centroid, which sits inside
        # Mammee Bay's circle — but the source's proximity search said Negril.
        n = normalize_one(_raw("Hampstead , St. Ann", "USD $300,000", hints=["negril"]))
        self.assertEqual(n.matched_regions, ["negril"])
        self.assertEqual(n.location_confidence, "proximity")

    def test_hinted_listing_still_respects_budget(self) -> None:
        n = normalize_one(_raw("Hampstead , St. Ann", "USD $900,000", hints=["upton"]))
        self.assertEqual(n.matched_regions, [])
        self.assertEqual(n.location_confidence, "proximity")

    def test_exact_coordinates_beat_hints(self) -> None:
        # Coordinates in the text are the Negril centre; the hint is wrong.
        n = normalize_one(_raw("Somewhere", "USD $300,000", hints=["upton"],
                               description="[coords: 18.273467, -78.340343]"))
        self.assertEqual(n.location_confidence, "exact")
        self.assertEqual(n.matched_regions, ["negril"])

    def test_no_hints_keeps_centroid_behaviour(self) -> None:
        n = normalize_one(_raw("Runaway Bay, St. Ann", "USD $300,000"))
        self.assertEqual(n.location_confidence, "approximate")
        self.assertIn("runaway_bay", n.matched_regions)


if __name__ == "__main__":
    unittest.main()
