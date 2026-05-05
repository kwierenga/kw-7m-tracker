from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "listings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    stable_id TEXT PRIMARY KEY,
    sources_json TEXT NOT NULL,
    urls_json TEXT NOT NULL,
    title TEXT,
    description TEXT,
    property_type TEXT,
    price_usd INTEGER,
    price_original TEXT,
    price_currency TEXT,
    lat REAL,
    lon REAL,
    location_text TEXT,
    location_confidence TEXT,
    matched_regions_json TEXT NOT NULL,
    keyword_boost INTEGER NOT NULL DEFAULT 0,
    listed_on_iso TEXT,
    photo_url TEXT,
    first_seen_iso TEXT NOT NULL,
    last_seen_iso TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen_iso);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen_iso);

CREATE TABLE IF NOT EXISTS run_log (
    run_iso TEXT PRIMARY KEY,
    n_scraped INTEGER,
    n_normalized INTEGER,
    n_new INTEGER,
    n_dropped INTEGER,
    notes TEXT,
    sources_json TEXT
);
"""


def _migrate(con: sqlite3.Connection) -> None:
    """Idempotent column adds for older DBs committed before the column existed."""
    cur = con.execute("PRAGMA table_info(run_log)")
    cols = {r[1] for r in cur.fetchall()}
    if "sources_json" not in cols:
        con.execute("ALTER TABLE run_log ADD COLUMN sources_json TEXT")


@contextmanager
def connect(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        _migrate(con)
        yield con
        con.commit()
    finally:
        con.close()


def upsert_listings(con: sqlite3.Connection, listings: Iterable[dict], run_iso: str) -> tuple[int, int]:
    """Returns (n_new, n_updated)."""
    n_new = n_updated = 0
    cur = con.cursor()
    for L in listings:
        existing = cur.execute(
            "SELECT first_seen_iso FROM listings WHERE stable_id = ?", (L["stable_id"],)
        ).fetchone()
        first_seen = existing["first_seen_iso"] if existing else run_iso
        cur.execute(
            """
            INSERT INTO listings (
                stable_id, sources_json, urls_json, title, description,
                property_type, price_usd, price_original, price_currency,
                lat, lon, location_text, location_confidence,
                matched_regions_json, keyword_boost,
                listed_on_iso, photo_url, first_seen_iso, last_seen_iso
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(stable_id) DO UPDATE SET
                sources_json=excluded.sources_json,
                urls_json=excluded.urls_json,
                title=excluded.title,
                description=excluded.description,
                property_type=excluded.property_type,
                price_usd=excluded.price_usd,
                price_original=excluded.price_original,
                price_currency=excluded.price_currency,
                lat=excluded.lat,
                lon=excluded.lon,
                location_text=excluded.location_text,
                location_confidence=excluded.location_confidence,
                matched_regions_json=excluded.matched_regions_json,
                keyword_boost=excluded.keyword_boost,
                listed_on_iso=COALESCE(excluded.listed_on_iso, listings.listed_on_iso),
                photo_url=COALESCE(excluded.photo_url, listings.photo_url),
                last_seen_iso=excluded.last_seen_iso
            """,
            (
                L["stable_id"],
                json.dumps(L["sources"]),
                json.dumps(L["urls"]),
                L["title"],
                L.get("description"),
                L.get("property_type"),
                L.get("price_usd"),
                L.get("price_original"),
                L.get("price_currency"),
                L.get("lat"),
                L.get("lon"),
                L.get("location_text"),
                L.get("location_confidence"),
                json.dumps(L.get("matched_regions", [])),
                1 if L.get("keyword_boost") else 0,
                L.get("listed_on_iso"),
                L.get("photo_url"),
                first_seen,
                run_iso,
            ),
        )
        if existing is None:
            n_new += 1
        else:
            n_updated += 1
    return n_new, n_updated


def listings_seen_in_run(con: sqlite3.Connection, run_iso: str) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM listings WHERE last_seen_iso = ?", (run_iso,))]


def listings_first_seen_in_run(con: sqlite3.Connection, run_iso: str) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM listings WHERE first_seen_iso = ?", (run_iso,))]


def listings_dropped_in_run(
    con: sqlite3.Connection,
    run_iso: str,
    sources_active: list[str] | None = None,
) -> list[dict]:
    """Listings present last run but not in this run.

    If sources_active is provided, exclude listings whose source set includes
    any source that did not successfully scrape this run. Bias toward silence
    rather than false 'dropped' alerts when a source flakes — under daily
    cadence transient failures are common and would otherwise spawn phantom
    drop events every time.
    """
    rows = con.execute(
        """
        SELECT * FROM listings
        WHERE last_seen_iso < ?
          AND last_seen_iso = (SELECT MAX(last_seen_iso) FROM listings WHERE last_seen_iso < ?)
        """,
        (run_iso, run_iso),
    ).fetchall()
    out = [dict(r) for r in rows]
    if sources_active is None:
        return out
    active = set(sources_active)
    confirmed: list[dict] = []
    for r in out:
        try:
            srcs = json.loads(r.get("sources_json") or "[]")
        except json.JSONDecodeError:
            srcs = []
        if srcs and all(s in active for s in srcs):
            confirmed.append(r)
    return confirmed


def write_run_log(
    con: sqlite3.Connection,
    run_iso: str,
    n_scraped: int,
    n_normalized: int,
    n_new: int,
    n_dropped: int,
    notes: str = "",
    sources_counts: dict[str, int] | None = None,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO run_log
        (run_iso, n_scraped, n_normalized, n_new, n_dropped, notes, sources_json)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            run_iso,
            n_scraped,
            n_normalized,
            n_new,
            n_dropped,
            notes,
            json.dumps(sources_counts or {}),
        ),
    )
