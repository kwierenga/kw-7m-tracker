"""Smoke tests for every scraper's _parse() function.

These run against captured HTML fixtures (no live network), and exist to catch
silent breakage when a site changes its layout — the scraper would still run
without errors but return 0 listings, which we'd never notice without these.

The captured fixtures are HOME pages for each site (smaller subset of the
listings the live scrapers fetch via paginated /property-search etc.), so
thresholds here are intentionally low.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.scrapers import (
    caribbean_mls,
    cb_jamaica,
    century21_jm,
    golden_gates,
    keez,
    millennium,
    realtor_com_intl,
    remax_elite,
    xposure_manual,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    p = FIXTURES / name
    if not p.exists():
        raise unittest.SkipTest(f"fixture not present: {p}")
    return p.read_text(encoding="utf-8")


class ParserSmokeTests(unittest.TestCase):
    """Each parser must return at least N listings from a known-good fixture."""

    def _check_minimum(self, listings, min_count: int, expected_source: str) -> None:
        self.assertGreaterEqual(
            len(listings),
            min_count,
            f"expected ≥{min_count} listings, got {len(listings)}",
        )
        for L in listings:
            self.assertEqual(L.source, expected_source)
            self.assertTrue(L.url, "every listing must have a URL")
            self.assertTrue(L.source_id, "every listing must have a source_id")

    def test_realtor_com_intl(self) -> None:
        listings = realtor_com_intl._parse(_load("realtor_com_intl.html"))
        self._check_minimum(listings, 10, "realtor_com_intl")

    def test_cb_jamaica(self) -> None:
        listings = cb_jamaica._parse(_load("cb_jamaica.html"))
        self._check_minimum(listings, 5, "cb_jamaica")

    def test_caribbean_mls(self) -> None:
        listings = caribbean_mls._parse(_load("caribbean_mls.html"))
        self._check_minimum(listings, 5, "caribbean_mls")
        # Sanity: at least one listing should have a parseable price string
        self.assertTrue(any(L.raw_price for L in listings))

    def test_millennium(self) -> None:
        listings = millennium._parse(_load("millennium.html"))
        self._check_minimum(listings, 3, "millennium")

    def test_golden_gates(self) -> None:
        listings = golden_gates._parse(_load("golden_gates.html"))
        self._check_minimum(listings, 4, "golden_gates")

    def test_century21_jm(self) -> None:
        listings = century21_jm._parse(_load("century21_jm.html"))
        self._check_minimum(listings, 3, "century21_jm")

    def test_remax_elite(self) -> None:
        listings = remax_elite._parse(_load("remax_elite.html"))
        self._check_minimum(listings, 10, "remax_elite")
        self.assertTrue(any(L.raw_price for L in listings))
        self.assertTrue(any(L.photo_url for L in listings))

    def test_keez(self) -> None:
        listings = keez._parse(_load("keez.json"))
        self._check_minimum(listings, 10, "keez")
        # JSON API gives us structured data, so most fields should be populated
        self.assertTrue(any(L.raw_price for L in listings))
        self.assertTrue(any(L.photo_url for L in listings))
        self.assertTrue(any(L.listed_on_iso for L in listings))
        # Coords embedded in description so normalize.py picks them up exact
        self.assertTrue(any(L.description and "[coords:" in L.description for L in listings))

    def test_xposure_interactive(self) -> None:
        listing = xposure_manual._parse(
            _load("xposure_interactive.html"),
            "https://jamaica.xposureapp.com/portal/jamaica/InteractiveLink?u=24481&l=98806",
            datetime.now(timezone.utc).isoformat(),
        )
        self.assertIsNotNone(listing)
        self.assertEqual(listing.source, "xposure")
        self.assertTrue(listing.raw_price, "xposure listing should have a price")


if __name__ == "__main__":
    unittest.main()
