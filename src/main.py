from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import scrapers
from .dedup import dedup
from .diff import classify
from .digest import build_digest, write_static_site
from .fx import get_jmd_per_usd
from .normalize import normalize_all
from .store import (
    connect,
    listings_dropped_in_run,
    listings_seen_in_run,
    upsert_listings,
    write_run_log,
)


def previous_run_iso(con) -> str | None:
    row = con.execute("SELECT MAX(run_iso) AS r FROM run_log").fetchone()
    return row["r"] if row else None


def run(dry_run: bool) -> int:
    run_iso = datetime.now(timezone.utc).isoformat()
    notes_lines: list[str] = []

    print(f"[run] starting run_iso={run_iso} dry_run={dry_run}")
    fx = get_jmd_per_usd()
    print(f"[fx] 1 USD = {fx:.2f} JMD")

    raws = []
    sources_active: list[str] = []
    for name, fn in scrapers.ALL_SCRAPERS:
        try:
            got = fn()
            print(f"[scrape] {name}: {len(got)} raw")
            raws.extend(got)
            sources_active.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"[scrape] {name}: FAILED {type(e).__name__}: {e}")
            notes_lines.append(f"{name} failed: {type(e).__name__}: {e}")

    norms = normalize_all(raws)
    print(f"[normalize] {len(norms)} normalized")

    matched = [n for n in norms if n.matched_regions]
    print(f"[filter] {len(matched)} matched at least one region")

    merged = dedup(matched)
    print(f"[dedup] {len(merged)} after dedup")

    with connect() as con:
        prev_run = previous_run_iso(con)
        print(f"[store] previous run = {prev_run}")
        rows_for_db = [asdict(L) | {"sources": L.sources, "urls": L.urls, "matched_regions": L.matched_regions} for L in merged]
        n_new_inserted, n_updated = upsert_listings(con, rows_for_db, run_iso)
        print(f"[store] inserted={n_new_inserted} updated={n_updated}")

        seen = listings_seen_in_run(con, run_iso)
        dropped = listings_dropped_in_run(con, run_iso) if prev_run else []
        buckets = classify(seen, dropped, run_iso, prev_run)
        print(f"[diff] new={len(buckets.new_this_week)} active={len(buckets.still_active)} dropped={len(buckets.dropped_off)}")

        write_run_log(con, run_iso, len(raws), len(merged), len(buckets.new_this_week), len(buckets.dropped_off), "; ".join(notes_lines))

    subject, html = build_digest(buckets, fx_rate=fx, sources=sources_active, run_iso=run_iso, notes="; ".join(notes_lines))
    print(f"[digest] {subject}")

    out_preview = Path(__file__).resolve().parent.parent / "data" / "last_digest.html"
    out_preview.write_text(html, encoding="utf-8")
    print(f"[digest] preview: {out_preview}")

    if dry_run:
        print("[digest] DRY RUN — not writing to docs/")
        return 0

    index = write_static_site(html, run_iso=run_iso)
    print(f"[digest] published: {index}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="don't update docs/, only data/last_digest.html")
    args = p.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
