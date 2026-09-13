"""caribbean_mls reads the site's MCP catalogue. These tests drive scrape()
through a fake transport: paging, rentals skipped, both response encodings,
and tool errors surfacing as failures."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from src.scrapers import caribbean_mls


def _row(i: int, **overrides) -> dict:
    row = {
        "id": f"id-{i}",
        "slug": f"house-{i}",
        "deal_type": "sale",
        "title": "3 Bedroom House for Sale, Runaway Bay, St Ann",
        "property_type_name": "House",
        "price": "450000.00",
        "price_currency": "USD",
        "map_lat": 18.46,
        "map_lng": -77.33,
        "map_source": "asset",
        "status": "active",
        "summary": "Sea view.",
        "zone_label": None,
    }
    row.update(overrides)
    return row


class _FakeCatalogue:
    def __init__(self, pages: dict[int, dict], *, sse: bool = False, tool_error: str | None = None):
        self.pages = pages
        self.sse = sse
        self.tool_error = tool_error
        self.methods: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.methods.append(body["method"])
        if "id" not in body:
            return httpx.Response(202)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}
        elif self.tool_error:
            result = {"content": [{"type": "text", "text": self.tool_error}], "isError": True}
        else:
            page = self.pages[body["params"]["arguments"]["offset"]]
            result = {"content": [{"type": "text", "text": json.dumps(page)}], "isError": False}
        payload = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if self.sse:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"event: message\ndata: {json.dumps(payload)}\n\n",
            )
        return httpx.Response(200, json=payload)

    def scrape(self):
        return caribbean_mls.scrape(transport=httpx.MockTransport(self.handler))


@patch.object(caribbean_mls, "REQUEST_GAP_S", 0)
class ScrapeTests(unittest.TestCase):
    def test_walks_every_page_and_skips_rentals(self):
        fake = _FakeCatalogue({
            0: {"results": [_row(1), _row(2, deal_type="rent")], "has_more": True, "next_offset": 25},
            25: {
                "results": [_row(3, price="50000000.00", price_currency="JMD", map_source="city"), _row(1)],
                "has_more": False,
            },
        })
        listings = fake.scrape()
        self.assertEqual([L.source_id for L in listings], ["id-1", "id-3"])
        self.assertEqual(fake.methods, ["initialize", "notifications/initialized", "tools/call", "tools/call"])

        house, jmd = listings
        self.assertEqual(house.url, "https://caribbeanrealestatemls.com/properties/house-1")
        self.assertEqual(house.raw_price, "USD 450,000")
        self.assertEqual(house.description, "Sea view. (18.46,-77.33)")
        self.assertEqual(house.status, "active")
        self.assertEqual(jmd.raw_price, "JMD 50,000,000")
        self.assertEqual(jmd.description, "Sea view.")  # city-centre coordinates not passed as exact

    def test_sse_encoded_responses_are_decoded(self):
        fake = _FakeCatalogue({0: {"results": [_row(1)], "has_more": False}}, sse=True)
        self.assertEqual(len(fake.scrape()), 1)

    def test_tool_error_raises(self):
        fake = _FakeCatalogue({}, tool_error="rate limit exceeded")
        with self.assertRaises(RuntimeError):
            fake.scrape()


class ParseRowsTests(unittest.TestCase):
    def test_type_prefixed_when_missing_from_title(self):
        [listing] = caribbean_mls._parse_rows([_row(1, title="Nonsuch, Portland", property_type_name="Land")], "t")
        self.assertEqual(listing.title, "Land — Nonsuch, Portland")

    def test_main_photo_resolved_against_media_host(self):
        media = [
            {"media_type": "image", "file": "/media/assets/media/b.jpg", "is_main": False},
            {"media_type": "image", "file": "/media/assets/media/a.jpg", "is_main": True},
        ]
        [listing] = caribbean_mls._parse_rows([_row(1, media=media)], "t")
        self.assertEqual(listing.photo_url, "https://api.caribbeanrealestatemls.com/media/assets/media/a.jpg")

    def test_missing_price_gives_no_raw_price(self):
        [listing] = caribbean_mls._parse_rows([_row(1, price=None)], "t")
        self.assertIsNone(listing.raw_price)


if __name__ == "__main__":
    unittest.main()
