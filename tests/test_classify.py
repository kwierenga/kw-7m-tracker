"""Tests for src/diff.py classify() — newness/stale/dropped bucketing.

The 'new' window is RECENTLY_NEW_DAYS days from first_seen_iso. A listing
discovered 2 mornings ago should still flash as 'new' on today's digest;
the previous rule retired it the day after discovery, which was the bug
that prompted this rewrite.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.diff import RECENTLY_NEW_DAYS, STALE_DAYS, classify


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _row(first_seen: datetime, *, listed_on: datetime | None = None, last_seen: datetime | None = None, sid: str = "x") -> dict:
    return {
        "stable_id": sid,
        "first_seen_iso": _iso(first_seen),
        "last_seen_iso": _iso(last_seen) if last_seen else _iso(first_seen),
        "listed_on_iso": _iso(listed_on) if listed_on else None,
    }


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        self.run_iso = _iso(self.now)

    def test_first_seen_today_is_new(self):
        rows = [_row(self.now, sid="A")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.new_since_last_run], ["A"])
        self.assertEqual(b.still_active, [])

    def test_first_seen_two_days_ago_is_still_new(self):
        # KENMEY case: discovered 2 mornings ago, prev_run was yesterday.
        # Under the old rule it retired to still_active the day after; under
        # the new rule it stays 'new' until RECENTLY_NEW_DAYS elapse.
        rows = [_row(self.now - timedelta(days=2), sid="kenmey")]
        prev = _iso(self.now - timedelta(days=1))
        b = classify(rows, [], self.run_iso, prev_run_iso=prev)
        self.assertEqual([r["stable_id"] for r in b.new_since_last_run], ["kenmey"])

    def test_first_seen_at_window_edge_is_still_new(self):
        # Edge: exactly RECENTLY_NEW_DAYS ago should still count (>= cutoff).
        rows = [_row(self.now - timedelta(days=RECENTLY_NEW_DAYS), sid="edge")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.new_since_last_run], ["edge"])

    def test_first_seen_outside_window_is_active(self):
        rows = [_row(self.now - timedelta(days=RECENTLY_NEW_DAYS + 1), sid="aged")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual(b.new_since_last_run, [])
        self.assertEqual([r["stable_id"] for r in b.still_active], ["aged"])

    def test_listed_on_does_not_make_old_first_seen_new(self):
        # New rule: only first_seen drives newness; a listing we discovered
        # last month doesn't re-flash as new just because listed_on bumps.
        rows = [_row(
            self.now - timedelta(days=30),
            listed_on=self.now - timedelta(days=1),
            sid="rebumped",
        )]
        b = classify(rows, [], self.run_iso)
        self.assertEqual(b.new_since_last_run, [])
        self.assertIn("rebumped", [r["stable_id"] for r in b.still_active])

    def test_listed_on_drives_stale_when_old(self):
        # listed_on says 6 months ago even though we just saw it: stale.
        rows = [_row(
            self.now - timedelta(days=2),
            listed_on=self.now - timedelta(days=STALE_DAYS + 5),
            sid="published-old",
        )]
        b = classify(rows, [], self.run_iso)
        # first_seen is recent → still flagged new (newness wins over stale,
        # which is intentional: a listing we just discovered is actionable
        # even if the source has had it on the page for ages).
        self.assertEqual([r["stable_id"] for r in b.new_since_last_run], ["published-old"])
        self.assertEqual(b.stale, [])

    def test_old_first_seen_no_listed_on_goes_stale(self):
        rows = [_row(self.now - timedelta(days=STALE_DAYS + 5), sid="abandoned")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.stale], ["abandoned"])
        self.assertEqual(b.still_active, [])

    def test_launch_cohort_old_first_seen_is_not_stale(self):
        # Listing first seen AT the tracker epoch with no listed_on: its true
        # age is unknown (it predated our watch), so tenure must not make it
        # stale — it stays active.
        epoch = self.now - timedelta(days=200)
        row = _row(epoch, sid="preexisting")  # first_seen == epoch
        b = classify([row], [], self.run_iso, tracker_epoch_iso=_iso(epoch))
        self.assertEqual([r["stable_id"] for r in b.still_active], ["preexisting"])
        self.assertEqual(b.stale, [])

    def test_appeared_after_epoch_old_first_seen_goes_stale(self):
        # Same age, but first seen well after the epoch → it genuinely appeared
        # during our watch and has been visible 90+ days → stale.
        epoch = self.now - timedelta(days=200)
        appeared = self.now - timedelta(days=150)  # > epoch + grace
        row = _row(appeared, sid="watched")
        b = classify([row], [], self.run_iso, tracker_epoch_iso=_iso(epoch))
        self.assertEqual([r["stable_id"] for r in b.stale], ["watched"])
        self.assertEqual(b.still_active, [])

    def test_launch_cohort_with_old_listed_on_still_stale(self):
        # A real source date is authoritative regardless of the epoch.
        epoch = self.now - timedelta(days=200)
        row = _row(epoch, listed_on=self.now - timedelta(days=STALE_DAYS + 5), sid="dated")
        b = classify([row], [], self.run_iso, tracker_epoch_iso=_iso(epoch))
        self.assertEqual([r["stable_id"] for r in b.stale], ["dated"])

    def test_recent_price_change_rescues_old_listing_from_stale(self):
        # Old enough to be stale, but the price moved within the stale window
        # → strong 'still live' evidence, so it stays active.
        row = _row(self.now - timedelta(days=STALE_DAYS + 5), sid="moved")
        row["canonical_id"] = "moved"
        changed = _iso(self.now - timedelta(days=10))
        b = classify([row], [], self.run_iso,
                     price_change_iso={"moved": changed})
        self.assertEqual([r["stable_id"] for r in b.still_active], ["moved"])
        self.assertEqual(b.stale, [])

    def test_old_price_change_does_not_rescue(self):
        # A price change that predates the stale window does not rescue.
        row = _row(self.now - timedelta(days=STALE_DAYS + 5), sid="longgone")
        row["canonical_id"] = "longgone"
        changed = _iso(self.now - timedelta(days=STALE_DAYS + 1))
        b = classify([row], [], self.run_iso,
                     price_change_iso={"longgone": changed})
        self.assertEqual([r["stable_id"] for r in b.stale], ["longgone"])
        self.assertEqual(b.still_active, [])

    def test_first_seen_missing_falls_through_to_active(self):
        # A row with no first_seen_iso (data corruption) shouldn't crash —
        # neither new nor stale, lands in active.
        rows = [{"stable_id": "broken", "first_seen_iso": None, "last_seen_iso": None}]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.still_active], ["broken"])
        self.assertEqual(b.new_since_last_run, [])
        self.assertEqual(b.stale, [])

    def test_dropped_passes_through(self):
        dropped = [_row(self.now - timedelta(days=10), sid="gone")]
        b = classify([], dropped, self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.dropped_off], ["gone"])

    def test_prev_run_iso_is_no_longer_consulted(self):
        # The old rule used prev_run_iso to gate newness. The new rule
        # doesn't — same row classifies the same regardless of prev_run.
        rows = [_row(self.now - timedelta(days=2), sid="A")]
        without = classify(rows, [], self.run_iso, prev_run_iso=None)
        yesterday = _iso(self.now - timedelta(days=1))
        with_prev = classify(rows, [], self.run_iso, prev_run_iso=yesterday)
        self.assertEqual(
            [r["stable_id"] for r in without.new_since_last_run],
            [r["stable_id"] for r in with_prev.new_since_last_run],
        )


if __name__ == "__main__":
    unittest.main()
