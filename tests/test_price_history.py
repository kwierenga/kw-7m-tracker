"""Tests for the day-over-day price-drop tracking in src/store.py.

The path under test is: upsert_listings writes to price_history (one row per
canonical_id per run that has a USD price), and find_price_drops compares the
two most recent rows per listing and returns those whose latest is lower.
"""
from __future__ import annotations

import sqlite3
import unittest

from src.store import (
    SCHEMA,
    _migrate,
    find_price_drops,
    last_price_change_iso,
    tracker_epoch_iso,
    upsert_listings,
)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _row(canonical: str, price_usd: int | None, *, stable_id: str | None = None) -> dict:
    return {
        "stable_id": stable_id or f"src:{canonical}",
        "canonical_id": canonical,
        "sources": ["src"],
        "urls": [f"https://example.com/{canonical}"],
        "title": f"Listing {canonical}",
        "description": None,
        "property_type": "home",
        "price_usd": price_usd,
        "price_original": f"${price_usd:,}" if price_usd is not None else None,
        "price_currency": "USD" if price_usd is not None else "unknown",
        "lat": None,
        "lon": None,
        "location_text": None,
        "location_confidence": "none",
        "matched_regions": ["upton"],
        "keyword_boost": False,
        "listed_on_iso": None,
        "photo_url": None,
        "contributing_source_ids": [("src", canonical)],
    }


class PriceHistoryTests(unittest.TestCase):
    def test_initial_upsert_writes_history_row(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        rows = con.execute("SELECT * FROM price_history WHERE canonical_id = 'A'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price_usd"], 500_000)

    def test_upsert_without_price_does_not_write_history(self):
        con = _connect()
        upsert_listings(con, [_row("A", None)], "2026-05-01T00:00:00Z")
        rows = con.execute("SELECT * FROM price_history WHERE canonical_id = 'A'").fetchall()
        self.assertEqual(len(rows), 0)

    def test_drop_detection_returns_old_and_new(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 450_000)], "2026-05-02T00:00:00Z")
        drops = find_price_drops(con, "2026-05-02T00:00:00Z")
        self.assertEqual(drops, {"A": (500_000, 450_000)})

    def test_no_change_is_not_a_drop(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 500_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(find_price_drops(con, "2026-05-02T00:00:00Z"), {})

    def test_increase_is_not_a_drop(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 525_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(find_price_drops(con, "2026-05-02T00:00:00Z"), {})

    def test_first_sighting_is_not_a_drop(self):
        # A listing first seen this run has only one history row, so the
        # last_two join finds no second row and excludes it.
        con = _connect()
        upsert_listings(con, [_row("A", 400_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(find_price_drops(con, "2026-05-02T00:00:00Z"), {})

    def test_drops_only_includes_listings_seen_this_run(self):
        # B dropped between t1 and t2 but wasn't observed at t3. A dropped
        # at t3. find_price_drops(t3) must return only A.
        con = _connect()
        upsert_listings(con, [_row("A", 500_000), _row("B", 600_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 500_000), _row("B", 550_000)], "2026-05-02T00:00:00Z")
        upsert_listings(con, [_row("A", 480_000)], "2026-05-03T00:00:00Z")
        drops = find_price_drops(con, "2026-05-03T00:00:00Z")
        self.assertIn("A", drops)
        self.assertNotIn("B", drops)
        self.assertEqual(drops["A"], (500_000, 480_000))

    def test_rerunning_same_run_iso_is_idempotent(self):
        # INSERT OR IGNORE on (canonical_id, run_iso) means a duplicate run
        # with a different price doesn't quietly overwrite the prior entry.
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 400_000)], "2026-05-01T00:00:00Z")
        rows = con.execute(
            "SELECT price_usd FROM price_history WHERE canonical_id = 'A'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price_usd"], 500_000)

    def test_drop_after_gap_run_with_no_price(self):
        # t1: $500k. t2: price unknown (not written to history). t3: $450k.
        # The two most recent history rows are t1=$500k, t3=$450k → drop.
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", None)], "2026-05-02T00:00:00Z")
        upsert_listings(con, [_row("A", 450_000)], "2026-05-03T00:00:00Z")
        self.assertEqual(
            find_price_drops(con, "2026-05-03T00:00:00Z"),
            {"A": (500_000, 450_000)},
        )


class TrackerEpochTests(unittest.TestCase):
    def test_none_when_empty(self):
        self.assertIsNone(tracker_epoch_iso(_connect()))

    def test_returns_earliest_first_seen(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-10T00:00:00Z")
        upsert_listings(con, [_row("B", 400_000)], "2026-05-03T00:00:00Z")
        upsert_listings(con, [_row("C", 300_000)], "2026-06-01T00:00:00Z")
        self.assertEqual(tracker_epoch_iso(con), "2026-05-03T00:00:00Z")


class LastPriceChangeTests(unittest.TestCase):
    def test_no_change_returns_empty(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 500_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(last_price_change_iso(con), {})

    def test_single_sighting_returns_empty(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        self.assertEqual(last_price_change_iso(con), {})

    def test_change_returns_run_of_change(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 450_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(last_price_change_iso(con), {"A": "2026-05-02T00:00:00Z"})

    def test_increase_counts_as_change(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 525_000)], "2026-05-02T00:00:00Z")
        self.assertEqual(last_price_change_iso(con), {"A": "2026-05-02T00:00:00Z"})

    def test_returns_most_recent_change(self):
        con = _connect()
        upsert_listings(con, [_row("A", 500_000)], "2026-05-01T00:00:00Z")
        upsert_listings(con, [_row("A", 450_000)], "2026-05-02T00:00:00Z")  # change
        upsert_listings(con, [_row("A", 450_000)], "2026-05-03T00:00:00Z")  # no change
        upsert_listings(con, [_row("A", 400_000)], "2026-05-04T00:00:00Z")  # change
        self.assertEqual(last_price_change_iso(con), {"A": "2026-05-04T00:00:00Z"})


if __name__ == "__main__":
    unittest.main()
