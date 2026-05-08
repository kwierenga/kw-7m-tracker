"""Generic detail-page extractor for the listing's own publication date.

Most JM real-estate sites only expose listed_on on the detail page, not the
search-results card. Rather than hand-rolling a parser for every source, we
try the patterns common across modern real-estate sites in priority order
and return the first hit. When no source has a structured publication date,
we fall back to plain-text labels ("Listed on", "Date Listed", etc).

If you find a site where this returns None despite having a visible date,
add the new pattern here rather than per-scraper — the value of one
generic extractor is that it benefits every source at once.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Iterable

from bs4 import BeautifulSoup

from .dates import parse_jamaica_date, to_iso

# Schema.org keys that real estate sites use for the listing's own publication
# date. Order matters: more-specific keys win over generic ones.
_JSONLD_DATE_KEYS = ("datePosted", "datePublished", "dateCreated", "validFrom")

# Plain-text labels that introduce the listing's posted date. Each pattern
# captures the date string after the label so parse_jamaica_date can take
# over (handles ISO, dd/mm/yyyy, and named-month forms).
_TEXT_LABELS = (
    "listed on",
    "date listed",
    "listed:",
    "posted on",
    "date posted",
    "date added",
    "added on",
    "available since",
    "available from",
)
# Capture up to ~25 chars after the label — enough for any reasonable date
# format including "September 15, 2026". The actual date parser handles
# rejecting non-date noise.
_TEXT_LABEL_RE = re.compile(
    r"(?i)(?:" + "|".join(re.escape(s) for s in _TEXT_LABELS) + r")[\s:]*([A-Za-z0-9 ,/\-\.]{6,30})",
)


def _walk_json(obj) -> Iterable:
    """Yield every dict value in obj (depth-first), regardless of nesting."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _from_jsonld(soup: BeautifulSoup) -> date | None:
    for script in soup.select('script[type="application/ld+json"]'):
        text = script.string or script.get_text() or ""
        if not text.strip():
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Some sites concatenate multiple JSON blocks or have trailing
            # commas; tolerating with a permissive scan rather than failing.
            continue
        for node in _walk_json(data):
            for key in _JSONLD_DATE_KEYS:
                val = node.get(key)
                if isinstance(val, str):
                    d = parse_jamaica_date(val)
                    if d:
                        return d
    return None


def _from_microdata(soup: BeautifulSoup) -> date | None:
    for key in _JSONLD_DATE_KEYS:
        el = soup.select_one(f'[itemprop="{key}"]')
        if not el:
            continue
        # itemprop on <meta> uses content=, on <time> uses datetime=, on plain
        # elements falls back to inner text. Try them all.
        candidate = el.get("content") or el.get("datetime") or el.get_text(" ", strip=True)
        d = parse_jamaica_date(candidate)
        if d:
            return d
    return None


def _from_og_meta(soup: BeautifulSoup) -> date | None:
    el = soup.select_one('meta[property="article:published_time"]') or soup.select_one(
        'meta[name="article:published_time"]'
    )
    if not el:
        return None
    return parse_jamaica_date(el.get("content"))


def _from_text_labels(soup: BeautifulSoup) -> date | None:
    text = soup.get_text(" ", strip=True)
    for m in _TEXT_LABEL_RE.finditer(text):
        candidate = m.group(1)
        d = parse_jamaica_date(candidate)
        if d:
            return d
    return None


def _from_first_time_tag(soup: BeautifulSoup) -> date | None:
    """Fall-back: first <time datetime="..."> on the page. Less specific
    than the labelled paths above, since it may be a navigation 'last
    updated' or footer date — but better than missing a date entirely
    on sites that mark their post date with a plain <time> tag."""
    for el in soup.find_all("time"):
        candidate = el.get("datetime") or el.get_text(" ", strip=True)
        d = parse_jamaica_date(candidate)
        if d:
            return d
    return None


def extract_listed_on(html: str) -> str | None:
    """Try several common patterns and return the first ISO date found.
    Returns None when the page has no recognizable publication date."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for finder in (_from_jsonld, _from_microdata, _from_og_meta, _from_text_labels, _from_first_time_tag):
        d = finder(soup)
        if d:
            return to_iso(d)
    return None
