from __future__ import annotations

import argparse
import json as _json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import scrapers
from .dedup import dedup
from .diff import classify, regions_for
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
    sources_counts: dict[str, int] = {}
    for name, fn in scrapers.ALL_SCRAPERS:
        try:
            got = fn()
            print(f"[scrape] {name}: {len(got)} raw")
            raws.extend(got)
            sources_active.append(name)
            sources_counts[name] = len(got)
        except Exception as e:  # noqa: BLE001
            print(f"[scrape] {name}: FAILED {type(e).__name__}: {e}")
            notes_lines.append(f"{name} failed: {type(e).__name__}: {e}")
            sources_counts[name] = -1  # sentinel: source did not run cleanly this cycle

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
        # Bug fix: only flag as dropped when ALL of a listing's sources scraped
        # successfully this run. Otherwise a transient failure spawns phantom
        # 'dropped' listings — and amplifies under daily cadence.
        dropped = (
            listings_dropped_in_run(con, run_iso, sources_active=sources_active)
            if prev_run else []
        )
        buckets = classify(seen, dropped, run_iso, prev_run)
        print(
            f"[diff] new={len(buckets.new_since_last_run)} "
            f"active={len(buckets.still_active)} "
            f"stale={len(buckets.stale)} "
            f"dropped={len(buckets.dropped_off)}"
        )

        write_run_log(
            con,
            run_iso,
            len(raws),
            len(merged),
            len(buckets.new_since_last_run),
            len(buckets.dropped_off),
            "; ".join(notes_lines),
            sources_counts=sources_counts,
        )

    subject, html = build_digest(
        buckets,
        fx_rate=fx,
        sources=sources_active,
        run_iso=run_iso,
        notes="; ".join(notes_lines),
        sources_counts=sources_counts,
    )
    print(f"[digest] {subject}")

    root = Path(__file__).resolve().parent.parent
    out_preview = root / "data" / "last_digest.html"
    out_preview.write_text(html, encoding="utf-8")
    print(f"[digest] preview: {out_preview}")

    # Per-region breakdown for the commit subject + day-over-day visibility.
    def _per_region(rows: list[dict]) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in rows:
            for slug in regions_for(row) or ["upton"]:
                out[slug] = out.get(slug, 0) + 1
        return out

    new_by_region = _per_region(buckets.new_since_last_run)
    dropped_by_region = _per_region(buckets.dropped_off)

    def _segment(per_region: dict[str, int], label: str) -> str | None:
        total = sum(per_region.values())
        if total == 0:
            return None
        if len(per_region) == 1:
            slug, n = next(iter(per_region.items()))
            return f"{n} {label} in {slug}"
        parts = ", ".join(
            f"{slug}: {n}"
            for slug, n in sorted(per_region.items(), key=lambda kv: -kv[1])
        )
        return f"{total} {label} ({parts})"

    segments = [
        s for s in (_segment(new_by_region, "new"), _segment(dropped_by_region, "dropped"))
        if s
    ]
    commit_subject = f"daily run {run_iso[:10]}"
    if segments:
        commit_subject += " — " + ", ".join(segments)

    # Status JSON consumed by the workflow to decide whether (and how) to commit.
    status = {
        "run_iso": run_iso,
        "new": len(buckets.new_since_last_run),
        "dropped": len(buckets.dropped_off),
        "active": len(buckets.still_active),
        "stale": len(buckets.stale),
        "new_by_region": new_by_region,
        "dropped_by_region": dropped_by_region,
        "sources_counts": sources_counts,
        "commit_subject": commit_subject,
    }
    (root / "data" / "last_run_status.json").write_text(
        _json.dumps(status, indent=2), encoding="utf-8"
    )
    print(f"[status] {commit_subject}")

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
