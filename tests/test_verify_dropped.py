"""Tests for the drop-verification logic in src/details.py.

The _classify_dropped_candidates helper is the pure decision core: given a
list of candidate dropped listings and a probe(url) -> status callable,
return (confirmed_dropped, false_drops). The verify_dropped wrapper just
injects a curl_cffi-backed probe and is exercised end-to-end during real
runs; we only test the classification core here.
"""
from __future__ import annotations

import unittest

from src.details import _classify_dropped_candidates


def _row(stable_id: str, urls: list[str]) -> dict:
    import json
    return {"stable_id": stable_id, "urls_json": json.dumps(urls)}


class ClassifyDroppedTests(unittest.TestCase):
    def test_404_only_url_is_confirmed_dropped(self):
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 404)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])
        self.assertEqual(false_drops, [])

    def test_410_is_also_confirmed(self):
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 410)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])

    def test_200_is_false_drop(self):
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 200)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_5xx_is_false_drop_silence_over_noise(self):
        # Server errors are ambiguous — a flaky 503 is not proof a listing is
        # dropped. Bias toward silence.
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 503)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_403_is_false_drop(self):
        # 403 may be a geo-block / WAF challenge, not a delisted page.
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 403)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_network_error_is_false_drop(self):
        # The probe contract: None means the request errored out (timeout,
        # connection reset, etc). Don't confirm a drop on uncertain signal.
        rows = [_row("A", ["https://example.com/a"])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: None)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_multi_source_all_dead_is_confirmed(self):
        rows = [_row("A", ["https://x.com/a", "https://y.com/a"])]
        confirmed, _ = _classify_dropped_candidates(rows, lambda u: 404)
        self.assertEqual([r["stable_id"] for r in confirmed], ["A"])

    def test_multi_source_one_alive_is_false_drop(self):
        # If ANY source URL still serves, the listing is alive somewhere —
        # don't claim it dropped just because one of its mirrors disappeared.
        rows = [_row("A", ["https://x.com/dead", "https://y.com/alive"])]
        statuses = {"https://x.com/dead": 404, "https://y.com/alive": 200}
        confirmed, false_drops = _classify_dropped_candidates(
            rows, lambda u: statuses[u]
        )
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_empty_url_list_is_false_drop(self):
        # No URLs to probe → no signal to confirm with. Default false-drop
        # so a borked DB row doesn't get incorrectly flagged.
        rows = [_row("A", [])]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 404)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_invalid_urls_json_is_false_drop(self):
        rows = [{"stable_id": "A", "urls_json": "{not json"}]
        confirmed, false_drops = _classify_dropped_candidates(rows, lambda u: 404)
        self.assertEqual(confirmed, [])
        self.assertEqual([r["stable_id"] for r in false_drops], ["A"])

    def test_empty_candidates_short_circuits(self):
        confirmed, false_drops = _classify_dropped_candidates([], lambda u: 404)
        self.assertEqual(confirmed, [])
        self.assertEqual(false_drops, [])

    def test_mix_of_confirmed_and_false(self):
        rows = [
            _row("A", ["https://x.com/a"]),
            _row("B", ["https://x.com/b"]),
            _row("C", ["https://x.com/c"]),
        ]
        statuses = {
            "https://x.com/a": 404,  # confirmed
            "https://x.com/b": 200,  # false
            "https://x.com/c": 410,  # confirmed
        }
        confirmed, false_drops = _classify_dropped_candidates(
            rows, lambda u: statuses[u]
        )
        self.assertEqual(sorted(r["stable_id"] for r in confirmed), ["A", "C"])
        self.assertEqual([r["stable_id"] for r in false_drops], ["B"])


if __name__ == "__main__":
    unittest.main()
