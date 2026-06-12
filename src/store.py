from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "listings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    stable_id TEXT PRIMARY KEY,
    canonical_id TEXT,
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
    last_seen_iso TEXT NOT NULL,
    detail_fetched_iso TEXT,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen_iso);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen_iso);
-- canonical_id index created in _migrate() after the column has been added on legacy DBs.

-- Maps every (source, source_id) we've ever observed to a canonical_id, so that
-- a property's identity survives transient source flakes. When dedup merges
-- listings across sources, all their (source, source_id) entries point to the
-- same canonical_id afterwards.
CREATE TABLE IF NOT EXISTS aliases (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON aliases(canonical_id);

CREATE TABLE IF NOT EXISTS run_log (
    run_iso TEXT PRIMARY KEY,
    n_scraped INTEGER,
    n_normalized INTEGER,
    n_new INTEGER,
    n_dropped INTEGER,
    notes TEXT,
    sources_json TEXT
);

-- One observation of (canonical_id, run_iso) → price_usd. Lets us detect
-- day-over-day price drops without keeping the full history on every row.
-- We write an entry for every run that has a price (INSERT OR IGNORE on the
-- PK so re-running the same run_iso is a no-op).
CREATE TABLE IF NOT EXISTS price_history (
    canonical_id TEXT NOT NULL,
    run_iso TEXT NOT NULL,
    price_usd INTEGER,
    price_original TEXT,
    price_currency TEXT,
    PRIMARY KEY (canonical_id, run_iso)
);
CREATE INDEX IF NOT EXISTS idx_price_history_canonical ON price_history(canonical_id);
"""


def _migrate(con: sqlite3.Connection) -> None:
    """Idempotent column adds for older DBs committed before the column existed."""
    cur = con.execute("PRAGMA table_info(run_log)")
    cols = {r[1] for r in cur.fetchall()}
    if "sources_json" not in cols:
        con.execute("ALTER TABLE run_log ADD COLUMN sources_json TEXT")

    cur = con.execute("PRAGMA table_info(listings)")
    listing_cols = {r[1] for r in cur.fetchall()}
    if "canonical_id" not in listing_cols:
        con.execute("ALTER TABLE listings ADD COLUMN canonical_id TEXT")
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_canonical "
            "ON listings(canonical_id) WHERE canonical_id IS NOT NULL"
        )
    if "detail_fetched_iso" not in listing_cols:
        # Marker for "we have looked at this listing's detail page". When
        # set, skip detail-fetching even if listed_on_iso is still NULL
        # (the page just doesn't expose a date) — otherwise we'd refetch
        # every run. Cleared (column wiped) only by manual DB surgery.
        con.execute("ALTER TABLE listings ADD COLUMN detail_fetched_iso TEXT")
    if "status" not in listing_cols:
        # Source's canonical availability status (see status.py). NULL = unknown.
        con.execute("ALTER TABLE listings ADD COLUMN status TEXT")

    # Backfill canonical_id for legacy rows: seed with stable_id (preserves
    # current identity) and seed aliases from the parsed source:source_id.
    rows = con.execute(
        "SELECT stable_id FROM listings WHERE canonical_id IS NULL"
    ).fetchall()
    for r in rows:
        sid = r[0]
        canonical = sid  # use existing stable_id as the seed canonical_id
        con.execute("UPDATE listings SET canonical_id = ? WHERE stable_id = ?", (canonical, sid))
        if ":" in sid:
            source, source_id = sid.split(":", 1)
            con.execute(
                "INSERT OR IGNORE INTO aliases (source, source_id, canonical_id) "
                "VALUES (?, ?, ?)",
                (source, source_id, canonical),
            )


def mint_canonical_id() -> str:
    return uuid.uuid4().hex


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


def lookup_canonical_id(con: sqlite3.Connection, source: str, source_id: str) -> str | None:
    row = con.execute(
        "SELECT canonical_id FROM aliases WHERE source = ? AND source_id = ?",
        (source, source_id),
    ).fetchone()
    return row[0] if row else None


def write_alias(con: sqlite3.Connection, source: str, source_id: str, canonical_id: str) -> None:
    """Idempotently set (source, source_id) → canonical_id. If a different
    canonical_id was previously recorded, this overwrites it (re-aliasing)."""
    con.execute(
        """
        INSERT INTO aliases (source, source_id, canonical_id) VALUES (?, ?, ?)
        ON CONFLICT(source, source_id) DO UPDATE SET canonical_id = excluded.canonical_id
        """,
        (source, source_id, canonical_id),
    )


def lookup_detail_state(
    con: sqlite3.Connection, canonical_ids: Iterable[str]
) -> dict[str, tuple[str | None, str | None]]:
    """For each canonical_id, return (listed_on_iso, detail_fetched_iso).
    Missing canonical_ids are absent from the result. Used by the detail-
    page fetcher to skip work for listings already enriched."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for cid in canonical_ids:
        if not cid:
            continue
        row = con.execute(
            "SELECT listed_on_iso, detail_fetched_iso FROM listings WHERE canonical_id = ?",
            (cid,),
        ).fetchone()
        if row:
            out[cid] = (row["listed_on_iso"], row["detail_fetched_iso"])
    return out


def reassign_aliases(con: sqlite3.Connection, old_canonical: str, new_canonical: str) -> None:
    """When dedup unifies two listings, point every alias of the loser at the winner.
    Also rename any listings row that still carries the loser canonical."""
    if old_canonical == new_canonical:
        return
    con.execute(
        "UPDATE aliases SET canonical_id = ? WHERE canonical_id = ?",
        (new_canonical, old_canonical),
    )
    con.execute(
        "DELETE FROM listings WHERE canonical_id = ?",
        (old_canonical,),
    )


def _record_price_history(
    con: sqlite3.Connection,
    canonical_id: str,
    run_iso: str,
    price_usd: int | None,
    price_original: str | None,
    price_currency: str | None,
) -> None:
    """Write one (canonical_id, run_iso) row when we have a USD price.
    INSERT OR IGNORE so re-running the same run_iso is harmless. We write on
    every observation rather than only on change, because the storage cost is
    trivial (~50 rows/day) and a flat per-run series makes the drop query
    straightforward (just compare last two rows)."""
    if price_usd is None:
        return
    con.execute(
        """
        INSERT OR IGNORE INTO price_history
        (canonical_id, run_iso, price_usd, price_original, price_currency)
        VALUES (?, ?, ?, ?, ?)
        """,
        (canonical_id, run_iso, price_usd, price_original, price_currency),
    )


def find_price_drops(
    con: sqlite3.Connection, run_iso: str
) -> dict[str, tuple[int, int]]:
    """Returns {canonical_id: (old_price_usd, new_price_usd)} for listings
    whose price decreased between the previous observation and this run.
    Only listings observed this run are considered; first-sightings (no
    prior history) and price increases are excluded."""
    rows = con.execute(
        """
        WITH last_two AS (
          SELECT canonical_id, run_iso, price_usd,
                 row_number() OVER (PARTITION BY canonical_id ORDER BY run_iso DESC) AS rn
          FROM price_history
          WHERE price_usd IS NOT NULL
        )
        SELECT a.canonical_id, b.price_usd AS old_p, a.price_usd AS new_p
        FROM last_two a
        JOIN last_two b
          ON b.canonical_id = a.canonical_id
         AND a.rn = 1 AND b.rn = 2
        WHERE a.run_iso = ?
          AND a.price_usd < b.price_usd
        """,
        (run_iso,),
    ).fetchall()
    return {r["canonical_id"]: (r["old_p"], r["new_p"]) for r in rows}


def tracker_epoch_iso(con: sqlite3.Connection) -> str | None:
    """The earliest first_seen we've ever recorded — i.e. when the tracker
    started observing. Used by diff.classify to tell whether a listing's
    first_seen reflects its real age (it appeared during our watch) or just
    our tenure (it already existed when we started, so its age is unknown)."""
    row = con.execute("SELECT MIN(first_seen_iso) AS e FROM listings").fetchone()
    return row["e"] if row else None


def last_price_change_iso(con: sqlite3.Connection) -> dict[str, str]:
    """Returns {canonical_id: run_iso} of the most recent run at which a
    listing's price *changed* from its previous observation (up or down).

    A recent price move is strong evidence a listing is still actively for
    sale — sellers adjust price to move unsold stock, while sold listings go
    static. diff.classify uses this to rescue an otherwise-stale (old) listing
    back into 'active'. Listings whose price has never changed are absent."""
    rows = con.execute(
        """
        WITH seq AS (
          SELECT canonical_id, run_iso, price_usd,
                 LAG(price_usd) OVER (
                   PARTITION BY canonical_id ORDER BY run_iso
                 ) AS prev_p
          FROM price_history
          WHERE price_usd IS NOT NULL
        )
        SELECT canonical_id, MAX(run_iso) AS last_change
        FROM seq
        WHERE prev_p IS NOT NULL AND price_usd <> prev_p
        GROUP BY canonical_id
        """
    ).fetchall()
    return {r["canonical_id"]: r["last_change"] for r in rows}


def upsert_listings(con: sqlite3.Connection, listings: Iterable[dict], run_iso: str) -> tuple[int, int]:
    """Returns (n_new, n_updated). Each listing must have a canonical_id assigned.
    Side effect: writes a price_history row per listing-with-price-this-run."""
    n_new = n_updated = 0
    cur = con.cursor()
    for L in listings:
        canonical = L["canonical_id"]
        # stable_id retained as a debug breadcrumb of which scraper the merged
        # listing's "primary" was at write time. Identity for dedup is canonical_id.
        stable = L.get("stable_id") or canonical
        existing = cur.execute(
            "SELECT first_seen_iso, stable_id FROM listings WHERE canonical_id = ?",
            (canonical,),
        ).fetchone()
        first_seen = existing["first_seen_iso"] if existing else run_iso
        if existing:
            cur.execute(
                """
                UPDATE listings SET
                    stable_id=?,
                    sources_json=?,
                    urls_json=?,
                    title=?,
                    description=?,
                    property_type=?,
                    price_usd=?,
                    price_original=?,
                    price_currency=?,
                    lat=?,
                    lon=?,
                    location_text=?,
                    location_confidence=?,
                    matched_regions_json=?,
                    keyword_boost=?,
                    listed_on_iso=COALESCE(?, listed_on_iso),
                    photo_url=COALESCE(?, photo_url),
                    last_seen_iso=?,
                    detail_fetched_iso=COALESCE(?, detail_fetched_iso),
                    status=COALESCE(?, status)
                WHERE canonical_id=?
                """,
                (
                    stable,
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
                    run_iso,
                    L.get("detail_fetched_iso"),
                    L.get("status"),
                    canonical,
                ),
            )
            n_updated += 1
        else:
            cur.execute(
                """
                INSERT INTO listings (
                    stable_id, canonical_id, sources_json, urls_json, title, description,
                    property_type, price_usd, price_original, price_currency,
                    lat, lon, location_text, location_confidence,
                    matched_regions_json, keyword_boost,
                    listed_on_iso, photo_url, first_seen_iso, last_seen_iso,
                    detail_fetched_iso, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(stable_id) DO UPDATE SET
                    canonical_id=excluded.canonical_id,
                    sources_json=excluded.sources_json,
                    urls_json=excluded.urls_json,
                    title=excluded.title,
                    last_seen_iso=excluded.last_seen_iso
                """,
                (
                    stable,
                    canonical,
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
                    L.get("detail_fetched_iso"),
                    L.get("status"),
                ),
            )
            n_new += 1

        # Persist aliases for every observed (source, source_id). The
        # contributing_source_ids list is set by main.py before we reach here.
        for source, source_id in L.get("contributing_source_ids", []):
            write_alias(con, source, source_id, canonical)

        _record_price_history(
            con,
            canonical,
            run_iso,
            L.get("price_usd"),
            L.get("price_original"),
            L.get("price_currency"),
        )
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
