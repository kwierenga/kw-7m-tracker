"""Decide which listings count as 'new since last run', 'still active', 'stale', 'dropped off'.

Definition of 'new': we discovered the listing within the last RECENTLY_NEW_DAYS
days (anchored on first_seen_iso). A 7-day window means a fresh hit stays
flagged as 'new' for a full week of daily digests, so the user has plenty of
mornings to notice it. The previous rule retired hits the day after they
were first seen, which under daily cadence felt too aggressive — a listing
first seen on Monday vanished from 'new' on Tuesday.

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

from .status import is_available

STALE_DAYS = 90
RECENTLY_NEW_DAYS = 7
# A listing's first_seen only reflects its real age if it appeared AFTER we
# started watching. Listings first seen within this many days of the tracker's
# epoch are treated as pre-existing (true age unknown), so their tenure doesn't
# drive staleness. Small grace absorbs sources that backfill over the first runs.
EPOCH_GRACE_DAYS = 2


@dataclass
class DiffBuckets:
    new_since_last_run: list[dict]
    still_active: list[dict]
    stale: list[dict]
    dropped_off: list[dict]
    # Listings the source itself marks as sold / under offer / expired. Held out
    # of new/active/stale regardless of age — the strongest available signal
    # that a listing is not genuinely for sale. See status.py.
    unavailable: list[dict]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Detail-extracted dates (e.g. "2026-05-15") parse as naive; treat them as
    # UTC so they can be compared against the tz-aware run cutoffs below.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def classify(
    seen_this_run: list[dict],
    dropped_rows: list[dict],
    run_iso: str,
    prev_run_iso: str | None = None,
    price_change_iso: dict[str, str] | None = None,
    likely_sold_rows: list[dict] | None = None,
    tracker_epoch_iso: str | None = None,
) -> DiffBuckets:
    now = _parse_iso(run_iso) or datetime.now(timezone.utc)
    new_cutoff = now - timedelta(days=RECENTLY_NEW_DAYS)
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    price_change_iso = price_change_iso or {}
    # first_seen counts as a real age anchor only when it lands after this — i.e.
    # the listing appeared during our watch, not before the tracker existed.
    epoch = _parse_iso(tracker_epoch_iso)
    reliable_first_cutoff = (
        epoch + timedelta(days=EPOCH_GRACE_DAYS) if epoch is not None else None
    )
    new: list[dict] = []
    active: list[dict] = []
    stale: list[dict] = []
    unavailable: list[dict] = []
    for row in seen_this_run:
        # The source's own status wins over any age heuristic: a sold/under-
        # offer/expired listing is not genuinely for sale no matter how fresh.
        if not is_available(row.get("status")):
            unavailable.append(row)
            continue
        listed = _parse_iso(row.get("listed_on_iso"))
        first = _parse_iso(row.get("first_seen_iso"))
        if first is not None and first >= new_cutoff:
            new.append(row)
            continue
        # Age anchor: the source's own posted date when known. Otherwise fall
        # back to first_seen — but only when it's a trustworthy age signal (the
        # listing appeared after our epoch). For the launch cohort, first_seen
        # just reflects our tenure, not the listing's age, so we leave the age
        # unknown and let status/price/disappearance signals speak instead of
        # fabricating staleness.
        reliable_first = first
        if (
            reliable_first is not None
            and reliable_first_cutoff is not None
            and reliable_first < reliable_first_cutoff
        ):
            reliable_first = None
        age_anchor = listed if listed is not None else reliable_first
        if age_anchor is not None and age_anchor < stale_cutoff:
            # Rescue from stale when the seller moved the price recently: a
            # price change within the stale window is strong evidence the
            # listing is still live, which beats the age heuristic.
            change = _parse_iso(price_change_iso.get(row.get("canonical_id") or ""))
            if change is not None and change >= stale_cutoff:
                active.append(row)
            else:
                stale.append(row)
        else:
            active.append(row)

    # Listings that vanished from a complete-coverage feed but whose page still
    # resolves — inferred 'likely sold'. Tagged so the digest shows the right
    # pill, then grouped with the other unavailable listings.
    for row in likely_sold_rows or []:
        row = dict(row)
        row["status"] = "likely_sold"
        unavailable.append(row)

    return DiffBuckets(
        new_since_last_run=new,
        still_active=active,
        stale=stale,
        dropped_off=list(dropped_rows),
        unavailable=unavailable,
    )


def regions_for(row: dict) -> list[str]:
    try:
        return json.loads(row.get("matched_regions_json") or "[]")
    except json.JSONDecodeError:
        return []
