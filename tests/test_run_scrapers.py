"""main.run_scrapers must record a scraper that raises OR silently returns
nothing as failed (-1, left out of sources_active). A silent 0 hid
caribbean_mls's 2026-09 site rebuild for weeks while the source still counted
as 'active' for drop detection."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import main


def _blocked():
    raise RuntimeError("no successful response (last status 403)")


class RunScrapersTests(unittest.TestCase):
    def test_empty_and_raising_scrapers_are_failed(self):
        fake = [("ok", lambda: ["a", "b"]), ("empty", lambda: []), ("blocked", _blocked)]
        raws, active, counts, notes = main.run_scrapers(fake)
        self.assertEqual(raws, ["a", "b"])
        self.assertEqual(active, ["ok"])
        self.assertEqual(counts, {"ok": 2, "empty": -1, "blocked": -1})
        self.assertEqual(len(notes), 2)
        self.assertIn("parsed 0 listings", notes[0])

    def test_source_allowed_to_be_empty_stays_active(self):
        with patch.object(main.scrapers, "MAY_RETURN_EMPTY", frozenset({"manual"})):
            _, active, counts, notes = main.run_scrapers([("manual", lambda: [])])
        self.assertEqual(active, ["manual"])
        self.assertEqual(counts, {"manual": 0})
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
