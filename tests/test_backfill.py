import tempfile
import unittest
from pathlib import Path

from src.store import connect, upsert_listings

EPOCH = "2026-05-01T00:00:00+00:00"
RUN = "2026-11-14T13:00:00+00:00"


def _row(cid: str, source: str) -> dict:
    return {
        "canonical_id": cid, "stable_id": f"{source}:{cid}", "sources": [source],
        "urls": [f"https://{source}/{cid}"], "title": cid, "matched_regions": ["upton"],
        "price_usd": 100_000, "price_original": "USD $100,000", "price_currency": "USD",
        "contributing_source_ids": [(source, cid)],
    }


class BackfillTests(unittest.TestCase):
    def test_backfilling_source_rows_are_backdated_to_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.db"
            with connect(path) as con:
                upsert_listings(con, [_row("a", "keez")], EPOCH)
            with connect(path) as con:
                upsert_listings(
                    con,
                    [_row("b", "remax_elite"), _row("c", "keez"), _row("a", "keez")],
                    RUN,
                    backdate_sources=frozenset({"remax_elite"}),
                    epoch_iso=EPOCH,
                )
                first = {
                    r["canonical_id"]: r["first_seen_iso"]
                    for r in con.execute("SELECT canonical_id, first_seen_iso FROM listings")
                }
            self.assertEqual(first["b"], EPOCH)  # backfilling source: epoch
            self.assertEqual(first["c"], RUN)  # other source: this run
            self.assertEqual(first["a"], EPOCH)  # existing row untouched

    def test_no_backdating_without_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with connect(Path(d) / "t.db") as con:
                upsert_listings(
                    con, [_row("b", "remax_elite")], RUN,
                    backdate_sources=frozenset({"remax_elite"}), epoch_iso=None,
                )
                self.assertEqual(con.execute("SELECT first_seen_iso FROM listings").fetchone()[0], RUN)


if __name__ == "__main__":
    unittest.main()
