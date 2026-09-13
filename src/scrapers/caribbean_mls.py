"""caribbeanrealestatemls.com — read through the site's public MCP catalogue.

The site was rebuilt in 2026-09: the Next.js __NEXT_DATA__ payload and the
/real-estate/ URLs the old HTML scraper relied on are gone, and its llms.txt
asks automated clients to query the read-only catalogue instead of scraping
pages. The catalogue returns the asking price in the source currency,
property-level coordinates and status. Anonymous limits are 20 requests/minute
and 25 rows per search, so a full Jamaica walk (~400 rows) is ~17 paced calls.

25-row pages exceed the server's payload ceiling, so it drops media from them —
most listings arrive without a photo.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import httpx

from ..models import RawListing
from ..status import normalize_status

SOURCE = "caribbean_mls"
BASE = "https://caribbeanrealestatemls.com"
MEDIA_BASE = "https://api.caribbeanrealestatemls.com"
MCP_URL = "https://mcp.caribbeanrealestatemls.com/mcp/"
MARKET = "jamaica"
PAGE_SIZE = 25  # server maximum per search
MAX_PAGES = 40  # 1,000 rows — ~2.5x the Jamaica inventory in 2026-09
REQUEST_GAP_S = 3.5  # keeps a full walk under the anonymous 20 requests/minute
PROTOCOL_VERSION = "2025-03-26"


def scrape(transport: httpx.BaseTransport | None = None) -> list[RawListing]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[RawListing] = []
    seen: set[str] = set()
    with httpx.Client(timeout=30, transport=transport) as client:
        catalogue = _Catalogue(client)
        catalogue.initialize()
        offset = 0
        for _ in range(MAX_PAGES):
            page = catalogue.call_tool(
                "catalog_search_properties",
                {"region": MARKET, "sort": "newest", "limit": PAGE_SIZE, "offset": offset},
            )
            for raw in _parse_rows(page.get("results") or [], fetched_at):
                # 'newest' order shifts when a listing is published mid-walk,
                # which can repeat a row across pages.
                if raw.source_id not in seen:
                    seen.add(raw.source_id)
                    out.append(raw)
            if not page.get("has_more"):
                break
            offset = page["next_offset"]
    return out


class _Catalogue:
    """Just enough of the MCP streamable-HTTP protocol to call tools."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._session_id: str | None = None
        self._request_id = 0
        self._last_request = float("-inf")

    def initialize(self) -> None:
        self._post({
            "jsonrpc": "2.0",
            "id": self._new_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "kw-7m-tracker", "version": "1.0"},
            },
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict) -> dict:
        msg = self._post({
            "jsonrpc": "2.0",
            "id": self._new_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in msg:
            raise RuntimeError(f"{SOURCE}: {name} failed: {msg['error']}")
        result = msg["result"]
        text = next((c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"), "")
        if result.get("isError"):
            raise RuntimeError(f"{SOURCE}: {name} returned an error: {text[:200]}")
        return json.loads(text)

    def _new_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, body: dict) -> dict:
        wait = REQUEST_GAP_S - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        headers = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        r = self._client.post(MCP_URL, json=body, headers=headers)
        self._last_request = time.monotonic()
        r.raise_for_status()
        self._session_id = r.headers.get("mcp-session-id", self._session_id)
        if "id" not in body:
            return {}  # a notification gets no response body
        return _decode(r)


def _decode(r: httpx.Response) -> dict:
    """A JSON-RPC response arrives either as plain JSON or as an SSE stream."""
    if "text/event-stream" in r.headers.get("content-type", ""):
        data = [line[5:].strip() for line in r.text.splitlines() if line.startswith("data:")]
        return json.loads(data[-1])
    return r.json()


def _parse_rows(rows: list[dict], fetched_at: str) -> list[RawListing]:
    out: list[RawListing] = []
    for row in rows:
        source_id = str(row.get("id") or "")
        slug = row.get("slug")
        if not source_id or not slug or row.get("deal_type") != "sale":
            continue

        title = row.get("title") or "(untitled)"
        ptype = row.get("property_type_name") or ""
        # Whole-word check — "Land" must not count as present in "Portland".
        if ptype and not re.search(rf"\b{re.escape(ptype)}\b", title, re.IGNORECASE):
            title = f"{ptype} — {title}"

        description = row.get("summary") or None
        lat, lon = row.get("map_lat"), row.get("map_lng")
        # 'asset' coordinates belong to the property itself; anything else is a
        # town or market centre, which normalize's own centroid lookup covers.
        if row.get("map_source") == "asset" and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            tag = f"({lat},{lon})"
            description = f"{description} {tag}" if description else tag

        # created_at is when the aggregator ingested the listing (its catalogue
        # was rebuilt in 2026-09), not the seller's listing date — so no
        # listed_on_iso, or every listing would look freshly posted.
        out.append(
            RawListing(
                source=SOURCE,
                source_id=source_id,
                url=f"{BASE}/properties/{slug}",
                title=title,
                raw_price=_raw_price(row),
                raw_location=row.get("zone_label") or None,
                description=description,
                fetched_at=fetched_at,
                photo_url=_main_photo(row),
                status=normalize_status(row.get("status")),
            )
        )
    return out


def _raw_price(row: dict) -> str | None:
    try:
        amount = float(row.get("price") or 0)
    except (TypeError, ValueError):
        return None
    currency = str(row.get("price_currency") or "").upper()
    if amount <= 0 or not currency:
        return None
    return f"{currency} {amount:,.0f}"


def _main_photo(row: dict) -> str | None:
    images = [m for m in row.get("media") or [] if m.get("media_type") == "image" and m.get("file")]
    if not images:
        return None
    main = next((m for m in images if m.get("is_main")), images[0])
    path = main["file"]
    return path if path.startswith("http") else MEDIA_BASE + path
