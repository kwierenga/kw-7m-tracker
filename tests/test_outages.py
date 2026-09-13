"""A failing source's listings drop out of the digest, so the page names the
outage: when the failure streak began and how many listings it hides."""
from __future__ import annotations

import json
import re
import sqlite3
import unittest

from src.diff import DiffBuckets
from src.digest import build_digest
from src.store import SCHEMA, _migrate, source_outages, write_run_log

RUN = "2026-07-16T13:00:00+00:00"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _day(day: int) -> str:
    return f"2026-07-{day:02d}T13:00:00+00:00"


def _log(con: sqlite3.Connection, day: int, **counts: int) -> None:
    write_run_log(con, _day(day), 0, 0, 0, 0, sources_counts=counts)


def _listing(con: sqlite3.Connection, cid: str, sources: list[str], last_seen_day: int) -> None:
    con.execute(
        "INSERT INTO listings (stable_id, canonical_id, sources_json, urls_json, "
        "matched_regions_json, first_seen_iso, last_seen_iso) VALUES (?, ?, ?, '[]', '[]', ?, ?)",
        (f"x:{cid}", cid, json.dumps(sources), _day(1), _day(last_seen_day)),
    )


class SourceOutagesTests(unittest.TestCase):
    def test_streak_start_and_hidden_listings(self):
        con = _connect()
        _log(con, 12, sagicor=900, keez=1000)
        _log(con, 13, sagicor=950, keez=1000)  # last good run
        _log(con, 14, sagicor=-1, keez=1000)
        _log(con, 15, sagicor=0, keez=1000)  # older runs logged a block as 0
        _log(con, 16, sagicor=-1, keez=1000)
        _listing(con, "A", ["sagicor"], 13)  # hidden by the outage
        _listing(con, "B", ["sagicor", "keez"], 16)  # re-confirmed by keez this run
        _listing(con, "C", ["sagicor"], 10)  # gone before the outage began
        _listing(con, "D", ["keez"], 13)
        self.assertEqual(
            source_outages(con, RUN),
            [{"source": "sagicor", "since_iso": _day(14), "hidden": 1}],
        )

    def test_healthy_run_reports_nothing(self):
        con = _connect()
        _log(con, 16, keez=1000, xposure=0)
        self.assertEqual(source_outages(con, RUN), [])

    def test_source_that_never_worked_hides_nothing(self):
        con = _connect()
        _log(con, 15, newsite=-1)
        _log(con, 16, newsite=-1)
        self.assertEqual(
            source_outages(con, RUN),
            [{"source": "newsite", "since_iso": _day(15), "hidden": 0}],
        )


class OutageNoticeTests(unittest.TestCase):
    @staticmethod
    def _render(outages: list[dict]) -> str:
        buckets = DiffBuckets([], [], [], [], [])
        return build_digest(
            buckets, fx_rate=158.0, sources=[], run_iso="2026-09-12T13:00:00+00:00", outages=outages
        )[1]

    def test_notice_names_source_duration_and_hidden_count(self):
        html = self._render([{"source": "sagicor_props", "since_iso": "2026-07-14T13:00:00+00:00", "hidden": 214}])
        notice = re.search(r'<div class="outage".*?</div>', html, re.S).group(0)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", notice))
        self.assertIn("1 source failing", text)
        self.assertIn("sagicor_props since 2026-07-14 (60 days)", text)
        self.assertIn("214 listings not shown", text)

    def test_no_notice_when_every_source_worked(self):
        self.assertNotIn('<div class="outage"', self._render([]))


if __name__ == "__main__":
    unittest.main()
