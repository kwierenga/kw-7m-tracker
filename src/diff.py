"""Decide which listings count as 'new since last run', 'still active', 'dropped off'.

Definition of 'new since last run':
  EITHER (preferred) the listing's own published date is within the last 7 days
                     AND we did not see it in our previous run,
  OR (fallback when no published date is exposed by the site)
                     this is the first run that observed the listing.

The 7-day published-date tolerance is intentionally wider than the daily run
cadence: sites publish 'new' listings with stale-by-a-few-days posted dates,
and we don't want to miss those just because we now scrape every day.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class DiffBuckets:
    new_since_last_run: list[dict]
    still_active: list[dict]
    dropped_off: list[dict]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_was_in_previous_run(row: dict, prev_run_iso: str | None) -> bool:
    if prev_run_iso is None:
        return False
    last = row.get("last_seen_iso")
    first = row.get("first_seen_iso")
    if last is None or first is None:
        return False
    return first <= prev_run_iso


def classify(seen_this_run: list[dict], dropped_rows: list[dict], run_iso: str, prev_run_iso: str | None) -> DiffBuckets:
    now = _parse_iso(run_iso) or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    new: list[dict] = []
    active: list[dict] = []
    for row in seen_this_run:
        listed = _parse_iso(row.get("listed_on_iso"))
        prior = _row_was_in_previous_run(row, prev_run_iso)
        is_new = False
        if listed is not None:
            if listed >= week_ago and not prior:
                is_new = True
        else:
            if not prior:
                is_new = True
        if is_new:
            new.append(row)
        else:
            active.append(row)
    return DiffBuckets(new_since_last_run=new, still_active=active, dropped_off=list(dropped_rows))


def regions_for(row: dict) -> list[str]:
    try:
        return json.loads(row.get("matched_regions_json") or "[]")
    except json.JSONDecodeError:
        return []
