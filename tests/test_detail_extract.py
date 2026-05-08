"""Tests for the generic listed_on extractor.

Synthetic HTML covering each pattern the extractor supports. When a real-site
fixture proves a pattern that's not covered here, add a synthetic test for it
so we don't lose the support to a regression.
"""
from __future__ import annotations

import unittest

from src.detail_extract import extract_listed_on


class ExtractListedOnTests(unittest.TestCase):
    def test_jsonld_date_posted(self):
        html = """
        <html><body><script type="application/ld+json">
        {"@type": "RealEstateListing", "datePosted": "2026-04-15"}
        </script></body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-04-15")

    def test_jsonld_nested_inside_graph(self):
        html = """
        <html><body><script type="application/ld+json">
        {"@graph": [{"@type": "WebPage"}, {"@type": "Product", "datePublished": "2026-03-01"}]}
        </script></body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-03-01")

    def test_jsonld_array_of_blocks(self):
        html = """
        <html><body><script type="application/ld+json">
        [{"@type": "Organization"}, {"@type": "RealEstateListing", "datePosted": "2026-02-10"}]
        </script></body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-02-10")

    def test_jsonld_invalid_json_does_not_crash(self):
        html = """
        <html><body><script type="application/ld+json">
        {bad json,
        </script>
        <p>Listed on 12 January 2026</p>
        </body></html>
        """
        # Falls through to text-label match
        self.assertEqual(extract_listed_on(html), "2026-01-12")

    def test_microdata_meta_tag(self):
        html = """
        <html><body>
        <meta itemprop="datePosted" content="2026-05-04">
        </body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-05-04")

    def test_microdata_time_element(self):
        html = """
        <html><body>
        <time itemprop="dateCreated" datetime="2026-01-20">January 20</time>
        </body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-01-20")

    def test_og_published_time(self):
        html = """
        <html><head>
        <meta property="article:published_time" content="2026-04-22T14:30:00Z">
        </head></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-04-22")

    def test_jsonld_full_iso_datetime(self):
        # Real-world JSON-LD almost always uses a full ISO datetime, not bare date.
        html = """
        <html><body><script type="application/ld+json">
        {"@type": "RealEstateListing", "datePosted": "2026-04-15T08:30:00+00:00"}
        </script></body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-04-15")

    def test_text_listed_on_named_month(self):
        html = "<html><body><p>Listed on April 15, 2026 by Acme Realty</p></body></html>"
        self.assertEqual(extract_listed_on(html), "2026-04-15")

    def test_text_date_listed_jamaica_dmy(self):
        # 03/05/2026 in JA convention is 3 May 2026
        html = "<html><body><div>Date Listed: 03/05/2026</div></body></html>"
        self.assertEqual(extract_listed_on(html), "2026-05-03")

    def test_text_posted_on_iso(self):
        html = "<html><body>Posted on 2026-06-01</body></html>"
        self.assertEqual(extract_listed_on(html), "2026-06-01")

    def test_text_added_on(self):
        html = "<html><body><span>Added on 1 February 2026</span></body></html>"
        self.assertEqual(extract_listed_on(html), "2026-02-01")

    def test_falls_back_to_first_time_tag(self):
        html = """
        <html><body>
        <time datetime="2026-07-10">posted</time>
        </body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-07-10")

    def test_jsonld_wins_over_text_label(self):
        # Both present — JSON-LD is preferred (more reliable than text).
        html = """
        <html><body>
        <script type="application/ld+json">
        {"datePosted": "2026-04-15"}
        </script>
        <p>Listed on January 1, 2020</p>
        </body></html>
        """
        self.assertEqual(extract_listed_on(html), "2026-04-15")

    def test_returns_none_when_no_date(self):
        html = "<html><body><h1>A house</h1><p>Beautiful, 3 beds</p></body></html>"
        self.assertIsNone(extract_listed_on(html))

    def test_empty_input(self):
        self.assertIsNone(extract_listed_on(""))
        self.assertIsNone(extract_listed_on(None))  # type: ignore[arg-type]

    def test_ignores_non_date_text_after_label(self):
        # "Listed on" followed by non-date text shouldn't crash or return junk
        html = "<html><body>Listed on the market for the first time. Wow!</body></html>"
        # The regex captures up to 30 chars after, parse_jamaica_date returns
        # None for non-date text, and we fall through to return None.
        self.assertIsNone(extract_listed_on(html))


if __name__ == "__main__":
    unittest.main()
