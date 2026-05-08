"""Parse dates from Jamaican listing sites.

Jamaica uses dd/mm/yyyy (UK/Commonwealth convention). Internally everything
travels as ISO 8601 (yyyy-mm-dd) which is unambiguous; this module is the only
place that turns ambiguous strings INTO ISO. Adjust here if a site is found
to use mm/dd/yyyy (some US-built plugins do, even on JA sites).

Strategy:
  1. Prefer ISO 8601 (yyyy-mm-dd) wherever a site exposes it (HTML <time> tags,
     JSON-LD, etc.) — unambiguous.
  2. Month-name forms ("3 May 2026", "May 3, 2026") — unambiguous.
  3. Pure numeric ("05/03/2026") — treated as dd/mm/yyyy by default. If the
     apparent month is > 12 we swap (defensive: a site really is mm/dd).
"""
from __future__ import annotations

import re
from datetime import date

# Trailing (?!\d) instead of \b: a `\b` requires a non-word char to follow,
# which fails on datetimes like "2026-04-22T14:30:00Z" (T is a word char).
# (?!\d) accepts T/space/end-of-string but still rejects digit-extension.
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?!\d)")
NUMERIC_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS.keys())
NAMED_DMY_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{2,4}})\b", re.IGNORECASE)
NAMED_MDY_RE = re.compile(rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{2,4}})\b", re.IGNORECASE)


def _year(s: str) -> int:
    y = int(s)
    return 2000 + y if y < 100 else y


def parse_jamaica_date(text: str | None) -> date | None:
    """Returns the date if found, else None. Treats ambiguous numeric dates as dd/mm/yyyy."""
    if not text:
        return None

    if m := ISO_RE.search(text):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    if m := NAMED_DMY_RE.search(text):
        try:
            return date(_year(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        except (ValueError, KeyError):
            pass

    if m := NAMED_MDY_RE.search(text):
        try:
            return date(_year(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        except (ValueError, KeyError):
            pass

    if m := NUMERIC_RE.search(text):
        try:
            a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
            # Default: dd/mm/yyyy (JA convention).
            d, mo = a, b
            # Defensive: if apparent month > 12 the site is using mm/dd; swap.
            if mo > 12 and d <= 12:
                d, mo = mo, d
            return date(y, mo, d)
        except ValueError:
            pass

    return None


def to_iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
