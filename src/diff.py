"""Decide which listings count as 'new since last run', 'still active', 'stale', 'dropped off'.

Definition of 'new': we discovered the listing within the last RECENTLY_NEW_DAYS
days (anchored on first_seen_iso). A 3-day window means a fresh hit stays
flagged as 'new' across a few daily digests, so the user has a few mornings
to notice it instead of one. The previous rule retired hits the day after
they were first seen, which under daily cadence felt too aggressive — a
listing first seen on Monday vanished from 'new' on Tuesday.

The source's own listed_on date is no longer used to flag 'new' (a listing's
visibility to the user is what matters, not the source's publication date).
listed_on still drives staleness via the >STALE_DAYS cutoff below.

Definition of 'stale': a listing whose age (source's listed_on when known,
otherwise our first_seen) is older than STALE_DAYS days. Jamaican real-estate
sites famously never take down sold listings, so anything sitting on a source
for 3+ months is probably gone in real life — collapse those into a separate
bucket so they don't drown out listings that might actually be available.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

STALE_DAYS = 90
RECENTLY_NEW_DAYS = 3


@dataclass
class DiffBuckets:
    new_since_last_run: list[dict]
    still_active: list[dict]
    stale: list[dict]
    dropped_off: list[dict]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify(
    seen_this_run: list[dict],
    dropped_rows: list[dict],
    run_iso: str,
    prev_run_iso: str | None = None,
) -> DiffBuckets:
    now = _parse_iso(run_iso) or datetime.now(timezone.utc)
    new_cutoff = now - timedelta(days=RECENTLY_NEW_DAYS)
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    new: list[dict] = []
    active: list[dict] = []
    stale: list[dict] = []
    for row in seen_this_run:
        listed = _parse_iso(row.get("listed_on_iso"))
        first = _parse_iso(row.get("first_seen_iso"))
        if first is not None and first >= new_cutoff:
            new.append(row)
            continue
        # Use the source's posted date when known, otherwise our first-seen.
        # A listing the source says is 6 months old goes straight to stale on
        # the day we discover it instead of waiting 90 days from first_seen.
        age_anchor = listed if listed is not None else first
        if age_anchor is not None and age_anchor < stale_cutoff:
            stale.append(row)
        else:
            active.append(row)
    return DiffBuckets(
        new_since_last_run=new,
        still_active=active,
        stale=stale,
        dropped_off=list(dropped_rows),
    )


def regions_for(row: dict) -> list[str]:
    try:
        return json.loads(row.get("matched_regions_json") or "[]")
    except json.JSONDecodeError:
        return []
