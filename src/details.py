"""Detail-page fetching for accurate listed_on dates.

Most JM real-estate sites only put the listing's own publication date on the
detail page, not the search-results card. Without a real listed_on date, the
"new since last run" classifier in diff.py falls back to first-seen-by-tracker
— which fires false alerts whenever a source flakes-and-recovers.

This module runs once per pipeline, between dedup and upsert. For listings
that match a region but lack listed_on_iso, it fetches the detail page,
extracts the date with the generic detail_extract.extract_listed_on, and
mutates the listing in place. The listings table records detail_fetched_iso
so we don't re-fetch on every run when a page genuinely has no date.

Politeness: per-source curl_cffi session with the same Throttle used by
scrapers (0.4s gap). Cap per source per run so first-time runs on a fresh
DB don't blow through the GitHub Actions budget (the cap is generous;
typical daily runs see only a handful of new listings).
"""
from __future__ import annotations

import json
from typing import Callable, Iterable

from curl_cffi import requests as cf

from .detail_extract import extract_listed_on
from .models import NormalizedListing
from .scrapers._throttle import Throttle, polite_get
from .store import lookup_detail_state

# Hard cap on detail fetches per source per run. A fresh DB has hundreds of
# matched listings; without a cap the daily run could exceed Actions limits.
# Listings beyond the cap simply get fetched on subsequent days as the
# already-fetched cache fills up.
MAX_FETCHES_PER_SOURCE = 40


def enrich_listed_on(
    con,
    listings: list[NormalizedListing],
    run_iso: str,
    max_per_source: int = MAX_FETCHES_PER_SOURCE,
) -> tuple[int, int]:
    """For each listing without listed_on_iso, look up the cache; if not
    cached, fetch the detail page and try to extract a date. Mutates
    listings in place. Returns (n_fetched, n_extracted)."""
    cache = lookup_detail_state(con, [L.canonical_id for L in listings if L.canonical_id])

    # Restore any cached values onto the in-memory listings — even when no date
    # was extractable last time, we want to remember "we tried" so we don't
    # re-fetch this run.
    targets: list[NormalizedListing] = []
    for L in listings:
        if L.listed_on_iso:
            continue
        cached = cache.get(L.canonical_id or "")
        if cached:
            cached_listed_on, cached_detail_iso = cached
            if cached_listed_on:
                L.listed_on_iso = cached_listed_on
            if cached_detail_iso:
                L.detail_fetched_iso = cached_detail_iso
                continue
        if not L.urls or not L.sources:
            continue
        targets.append(L)

    if not targets:
        return 0, 0

    by_source: dict[str, list[NormalizedListing]] = {}
    for L in targets:
        by_source.setdefault(L.sources[0], []).append(L)

    n_fetched = n_extracted = 0
    for source, items in by_source.items():
        items = items[:max_per_source]
        throttle = Throttle()
        try:
            with cf.Session(impersonate="chrome131") as s:
                for L in items:
                    url = L.urls[0]
                    try:
                        r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                    except Exception:  # noqa: BLE001
                        continue
                    if r.status_code != 200:
                        # Mark as fetched so we don't loop on a 404 every run.
                        # Real network/rate-limit errors are signaled by exception
                        # above and skipped (will retry next run).
                        if r.status_code == 404:
                            L.detail_fetched_iso = run_iso
                        continue
                    n_fetched += 1
                    iso = extract_listed_on(r.text)
                    if iso:
                        L.listed_on_iso = iso
                        n_extracted += 1
                    L.detail_fetched_iso = run_iso
        except Exception:  # noqa: BLE001
            # Source-level failure (DNS, etc) — leave remaining items unmarked
            # so they get retried on the next run.
            continue

    return n_fetched, n_extracted


# Status codes we treat as conclusive evidence the URL no longer maps to a
# listing. Other 4xx (e.g. 403/451) might be transient rate-limit / geo-block
# noise, so we don't trust them as drop signals.
_DEAD_STATUSES = (404, 410)

ProbeFn = Callable[[str], int | None]


def _classify_dropped_candidates(
    candidates: list[dict], probe: ProbeFn
) -> tuple[list[dict], list[dict]]:
    """Pure decision logic, separated from HTTP for testability. A listing is
    confirmed dropped only when EVERY one of its source URLs probes as dead
    (404/410). Any 200, redirect, 5xx, network error, or empty URL list falls
    through to the false-drops bucket — biasing toward silence per the same
    rationale as listings_dropped_in_run's flake guard."""
    confirmed: list[dict] = []
    false_drops: list[dict] = []
    for row in candidates:
        try:
            urls = json.loads(row.get("urls_json") or "[]")
        except json.JSONDecodeError:
            urls = []
        if not urls:
            false_drops.append(row)
            continue
        if all(probe(u) in _DEAD_STATUSES for u in urls):
            confirmed.append(row)
        else:
            false_drops.append(row)
    return confirmed, false_drops


def verify_dropped(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """For each candidate dropped listing, fetch its source URL(s) and only
    confirm the drop when every URL returns 404/410. Returns
    (confirmed_dropped, false_drops). The candidate count is small in
    practice (single-digit per run) so a one-off session with the same
    Throttle scrapers use is fine."""
    if not candidates:
        return [], []
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        def _probe(url: str) -> int | None:
            try:
                r = polite_get(s, url, throttle, allow_redirects=True, timeout=30)
                return r.status_code
            except Exception:  # noqa: BLE001
                return None

        return _classify_dropped_candidates(candidates, _probe)
