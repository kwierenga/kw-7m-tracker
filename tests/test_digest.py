"""Digest rendering: headline totals count unique listings (the region radii
overlap, so one listing renders under several regions), and scraped text is
HTML-escaped."""
from __future__ import annotations

import json
import re
import unittest

from src.diff import DiffBuckets
from src.digest import build_digest

RUN = "2026-09-12T13:00:00+00:00"


def _row(
    cid: str,
    *,
    regions: list[str],
    title: str = "House for sale",
    url: str = "https://example.com/listing",
    photo: str | None = None,
) -> dict:
    return {
        "canonical_id": cid,
        "stable_id": f"keez:{cid}",
        "sources_json": json.dumps(["keez"]),
        "urls_json": json.dumps([url]),
        "title": title,
        "property_type": "home",
        "price_usd": 300_000,
        "price_original": "USD $300,000",
        "price_currency": "USD",
        "location_text": "Runaway Bay, St. Ann",
        "location_confidence": "exact",
        "matched_regions_json": json.dumps(regions),
        "keyword_boost": 0,
        "listed_on_iso": None,
        "photo_url": photo,
        "first_seen_iso": RUN,
        "status": None,
    }


def _render(new=(), active=()) -> tuple[str, str]:
    buckets = DiffBuckets(
        new_since_last_run=list(new),
        still_active=list(active),
        stale=[],
        dropped_off=[],
        unavailable=[],
    )
    return build_digest(buckets, fx_rate=158.0, sources=["keez"], run_iso=RUN, sources_counts={"keez": 2})


class HeadlineTotalsTests(unittest.TestCase):
    def test_listing_in_overlapping_regions_counts_once(self):
        subject, html = _render(
            new=[_row("A", regions=["runaway_bay", "discovery_bay"])],
            active=[_row("B", regions=["runaway_bay", "discovery_bay", "mammee_bay"])],
        )
        summary = re.search(r'<p class="summary">(.*?)</p>', html, re.S).group(1)
        self.assertIn("1 new", summary)
        self.assertIn("1 still active", summary)
        self.assertIn("— 1 new (", subject)
        # ...while each matching region still shows the listing.
        self.assertEqual(html.count('data-id="A"'), 2)


class EscapingTests(unittest.TestCase):
    def test_scraped_title_is_escaped(self):
        _, html = _render(new=[_row("A", regions=["upton"], title='<img src=x onerror="alert(1)"> & Co')])
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x onerror=&#34;alert(1)&#34;&gt; &amp; Co", html)

    def test_non_http_urls_are_not_rendered(self):
        _, html = _render(
            new=[_row("A", regions=["upton"], url="javascript:alert(1)", photo="javascript:alert(2)")]
        )
        self.assertNotIn("javascript:", html)


if __name__ == "__main__":
    unittest.main()
