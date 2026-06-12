"""Tests for the drop-verification logic in src/details.py.

_classify_dropped_candidates is the pure decision core: given candidate dropped
listings and a probe(url) -> status callable, split them into
(confirmed_dropped, likely_sold, false_drops). verify_dropped just injects a
curl_cffi-backed probe; we test the classification core here.

- confirmed_dropped: every URL is dead (404/410).
- likely_sold: every URL still serves (200) AND every source is complete-coverage.
- false_drops: everything else (ambiguous → silence).
"""
from __future__ import annotations

import json
import unittest

from src.details import _classify_dropped_candidates

COMPLETE = frozenset({"keez"})


def _row(stable_id: str, urls: list[str], sources: list[str] | None = None) -> dict:
    row = {"stable_id": stable_id, "urls_json": json.dumps(urls)}
    if sources is not None:
        row["sources_json"] = json.dumps(sources)
    return row


class ClassifyDroppedTests(unittest.TestCase):
    def test_404_only_url_is_confirmed_dropped(self):
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(rows, lambda u: 404)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])
        self.assertEqual(likely, [])
        self.assertEqual(false_drops, [])

    def test_410_is_also_confirmed(self):
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, _likely, _false = _classify_dropped_candidates(rows, lambda u: 410)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])

    def test_200_complete_source_is_likely_sold(self):
        # Vanished from a complete-coverage feed but page still serves → sold.
        rows = [_row("A", ["https://example.com/a"], sources=["keez"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: 200, COMPLETE
        )
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in likely], ["A"])
        self.assertEqual(false_drops, [])

    def test_200_coverage_limited_source_is_false_drop(self):
        # realtor.com rotates its window — a 200 vanish is not a sale.
        rows = [_row("A", ["https://example.com/a"], sources=["realtor_com_intl"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: 200, COMPLETE
        )
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_200_no_complete_set_is_false_drop(self):
        # Without a complete-coverage allowlist, a 200 never counts as sold.
        rows = [_row("A", ["https://example.com/a"], sources=["keez"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(rows, lambda u: 200)
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_likely_sold_requires_all_sources_complete(self):
        # Mixed sources: one complete, one limited → not trustworthy → false.
        rows = [_row("A", ["https://x/a"], sources=["keez", "realtor_com_intl"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: 200, COMPLETE
        )
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_5xx_is_false_drop_silence_over_noise(self):
        rows = [_row("A", ["https://example.com/a"], sources=["keez"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: 503, COMPLETE
        )
        self.assertEqual(confirmed, [])
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_403_is_false_drop(self):
        rows = [_row("A", ["https://example.com/a"], sources=["keez"])]
        _c, likely, false_drops = _classify_dropped_candidates(rows, lambda u: 403, COMPLETE)
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_network_error_is_false_drop(self):
        rows = [_row("A", ["https://example.com/a"], sources=["keez"])]
        _c, likely, false_drops = _classify_dropped_candidates(rows, lambda u: None, COMPLETE)
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_multi_url_all_dead_is_confirmed(self):
        rows = [_row("A", ["https://x.com/a", "https://y.com/a"], sources=["keez"])]
        confirmed, _likely, _false = _classify_dropped_candidates(rows, lambda u: 404, COMPLETE)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])

    def test_multi_url_one_dead_one_alive_is_false_drop(self):
        # Mixed dead+alive is neither fully gone nor cleanly live → silence.
        rows = [_row("A", ["https://x.com/dead", "https://y.com/alive"], sources=["keez"])]
        statuses = {"https://x.com/dead": 404, "https://y.com/alive": 200}
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: statuses[u], COMPLETE
        )
        self.assertEqual(confirmed, [])
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_empty_url_list_is_false_drop(self):
        rows = [_row("A", [], sources=["keez"])]
        confirmed, likely, false_drops = _classify_dropped_candidates(rows, lambda u: 404, COMPLETE)
        self.assertEqual(confirmed, [])
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_invalid_urls_json_is_false_drop(self):
        rows = [{"stable_id": "A", "urls_json": "{not json"}]
        confirmed, likely, false_drops = _classify_dropped_candidates(rows, lambda u: 404, COMPLETE)
        self.assertEqual(confirmed, [])
        self.assertEqual(likely, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_empty_candidates_short_circuits(self):
        confirmed, likely, false_drops = _classify_dropped_candidates([], lambda u: 404, COMPLETE)
        self.assertEqual(confirmed, [])
        self.assertEqual(likely, [])
        self.assertEqual(false_drops, [])

    def test_mix_of_all_three_outcomes(self):
        rows = [
            _row("A", ["https://x.com/a"], sources=["keez"]),              # 404 → confirmed
            _row("B", ["https://x.com/b"], sources=["keez"]),              # 200 complete → likely sold
            _row("C", ["https://x.com/c"], sources=["realtor_com_intl"]),  # 200 limited → false
        ]
        statuses = {"https://x.com/a": 404, "https://x.com/b": 200, "https://x.com/c": 200}
        confirmed, likely, false_drops = _classify_dropped_candidates(
            rows, lambda u: statuses[u], COMPLETE
        )
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])
        self.assertEqual([r["stable_id"] for r in likely], ["B"])
        self.assertEqual([r["stable_id"] for r in false_drops], ["C"])


if __name__ == "__main__":
    unittest.main()
