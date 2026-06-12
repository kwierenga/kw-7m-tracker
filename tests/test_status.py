"""Tests for src/status.py and the 'unavailable' bucket in diff.classify."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.diff import STALE_DAYS, classify
from src.status import is_available, merge_status, normalize_status


class NormalizeStatusTests(unittest.TestCase):
    def test_unknown_and_empty(self):
        for raw in (None, "", "   ", "Private Treaty", "Foreclosure"):
            self.assertIsNone(normalize_status(raw), raw)

    def test_sold(self):
        for raw in ("Sold", "SOLD", "Status: Sold"):
            self.assertEqual(normalize_status(raw), "sold", raw)

    def test_under_offer_variants(self):
        for raw in ("Under Offer", "Under Contract", "Pending", "Reserved", "Under Negotiation"):
            self.assertEqual(normalize_status(raw), "under_offer", raw)

    def test_expired(self):
        self.assertEqual(normalize_status("Expired"), "expired")

    def test_active_variants(self):
        for raw in ("Sale", "For Sale", "Active", "Available", "New", "Price Drop"):
            self.assertEqual(normalize_status(raw), "active", raw)

    def test_sold_wins_over_sale_substring(self):
        # 'Sold' must not be misread as active even though both relate to sale.
        self.assertEqual(normalize_status("Sold — was For Sale"), "sold")


class IsAvailableTests(unittest.TestCase):
    def test_available(self):
        self.assertTrue(is_available(None))
        self.assertTrue(is_available("active"))

    def test_not_available(self):
        for s in ("sold", "under_offer", "expired"):
            self.assertFalse(is_available(s), s)


class MergeStatusTests(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(merge_status("active", "sold"), "sold")
        self.assertEqual(merge_status("sold", "under_offer"), "sold")
        self.assertEqual(merge_status("under_offer", "expired"), "under_offer")
        self.assertEqual(merge_status(None, "active"), "active")
        self.assertEqual(merge_status(None, None), None)


class ClassifyUnavailableTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
        self.run_iso = self.now.isoformat()

    def _row(self, *, status=None, first_seen=None, sid="x"):
        fs = first_seen or self.now
        return {
            "stable_id": sid,
            "first_seen_iso": fs.isoformat(),
            "last_seen_iso": fs.isoformat(),
            "listed_on_iso": None,
            "status": status,
        }

    def test_sold_routes_to_unavailable_not_new(self):
        # Fresh first_seen would normally be 'new'; sold status overrides.
        rows = [self._row(status="sold", sid="S")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.unavailable], ["S"])
        self.assertEqual(b.new_since_last_run, [])
        self.assertEqual(b.still_active, [])

    def test_under_offer_overrides_stale(self):
        # Old enough to be stale, but under offer → unavailable, not stale.
        old = self.now - timedelta(days=STALE_DAYS + 10)
        rows = [self._row(status="under_offer", first_seen=old, sid="U")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual([r["stable_id"] for r in b.unavailable], ["U"])
        self.assertEqual(b.stale, [])

    def test_active_and_unknown_stay_in_normal_buckets(self):
        rows = [self._row(status="active", sid="A"), self._row(status=None, sid="N")]
        b = classify(rows, [], self.run_iso)
        self.assertEqual(b.unavailable, [])
        self.assertEqual({r["stable_id"] for r in b.new_since_last_run}, {"A", "N"})

    def test_likely_sold_rows_join_unavailable_tagged(self):
        gone = {"stable_id": "G", "canonical_id": "G", "first_seen_iso": None,
                "last_seen_iso": None, "listed_on_iso": None, "status": None}
        b = classify([], [], self.run_iso, likely_sold_rows=[gone])
        self.assertEqual([r["stable_id"] for r in b.unavailable], ["G"])
        self.assertEqual(b.unavailable[0]["status"], "likely_sold")

    def test_likely_sold_does_not_mutate_caller_row(self):
        gone = {"stable_id": "G", "status": None}
        classify([], [], self.run_iso, likely_sold_rows=[gone])
        self.assertIsNone(gone["status"])  # classify copied the row, didn't mutate


class ScraperStatusExtractionTests(unittest.TestCase):
    def test_keez_maps_expired_status(self):
        import json

        from src.scrapers import keez

        payload = json.dumps({"data": [
            {"id": 1, "url": "https://x/1", "rent_sale": "sale", "status_name": "Active",
             "currency": "USD", "price_current": 100000, "address": {}},
            {"id": 2, "url": "https://x/2", "rent_sale": "sale", "status_name": "Expired",
             "currency": "USD", "price_current": 200000, "address": {}},
        ]})
        by_id = {L.source_id: L for L in keez._parse(payload)}
        self.assertEqual(by_id["1"].status, "active")
        self.assertEqual(by_id["2"].status, "expired")

    def test_remax_reads_under_offer_badge(self):
        from src.scrapers import remax_elite

        html = """
        <div class="propertysearch_pb">
          <div class="badge_wrap"><span class="txt-infoRed">Sale</span><span>Under Offer</span></div>
          <a class="link_absolute_internal" href="/property/Some-Home/MLS-123"></a>
          <input class="acronym_id" value="MLS-123">
          <div class="box-collectionHomeDetails"><h5>Runaway Bay</h5><p>US$300,000</p></div>
          <h4>House</h4>
        </div>
        <div class="propertysearch_pb">
          <div class="badge_wrap"><span class="txt-infoRed">Sale</span></div>
          <a class="link_absolute_internal" href="/property/Other-Home/MLS-999"></a>
          <input class="acronym_id" value="MLS-999">
          <div class="box-collectionHomeDetails"><h5>Discovery Bay</h5><p>US$250,000</p></div>
          <h4>House</h4>
        </div>
        """
        by_id = {L.source_id: L for L in remax_elite._parse(html)}
        self.assertEqual(by_id["MLS-123"].status, "under_offer")
        self.assertEqual(by_id["MLS-999"].status, "active")


if __name__ == "__main__":
    unittest.main()
