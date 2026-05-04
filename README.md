# kw-7m-tracker

Weekly property-listings tracker for the Upton Estate Golf & Country Club area in Jamaica. Scrapes 7 sources, dedups, filters by 7-mile radius + budget, publishes a digest to GitHub Pages.

**Live page:** https://kwierenga.github.io/kw-7m-tracker/

## Why this exists

Jamaican real-estate sites rarely take down sold listings, so old postings clutter results. The whole point of this tracker is **detecting fresh listings** — properties that weren't in last week's run AND (where the site exposes a listed-on date) were published within the last 7 days. Dedup is a digest-cleanliness feature, not the main signal.

## Search parameters

Configured in [`src/regions.py`](src/regions.py):

- **Center:** Upton Estate Golf & Country Club clubhouse — `18.38427930703869, -77.06401634785209`
- **Radius:** 7 miles
- **Budget:** homes ≤ $800K USD, land ≤ $350K USD
- **Boost keywords:** "upton estate", "upton", "sandals golf", "sandals", "golf course", "country club"

Multi-region is built in — adding another spot in Jamaica is a one-line entry in `REGIONS`.

## Architecture

```
GitHub Actions cron (Sundays 13:00 UTC)
   │
   ├─► curl_cffi scrapers (chrome131 TLS fingerprint) ──► RawListing[]
   │
   ├─► Normalize: geocode, JMD→USD via daily FX, dedup, region-match, keyword boost
   │
   ├─► SQLite (data/listings.db, committed weekly — git is the history)
   │
   ├─► Diff: classify each listing as new-this-week / still-active / dropped-off
   │
   └─► Render docs/index.html + docs/archive/<date>.html → GitHub Pages
       Notification: GitHub commit emails (no SendGrid/SMTP needed)
```

## Sources scraped

| Source | Status | Notes |
|---|---|---|
| realtor.com international Jamaica | ✅ active | ~25 cards/page, server-rendered |
| caribbeanrealestatemls.com | ✅ active | Next.js, listings in `__NEXT_DATA__` JSON |
| cbjamaica.com (Coldwell Banker JA) | ✅ active | Featured + recent properties |
| millennium properties | ✅ active | `/property-search?page=N` paginated |
| golden gates realty JA | ✅ active | Same template as Millennium |
| century21jm.com | ⚠️ partial | Home only (5 cards) — pagination URL pattern still unknown |
| xposure InteractiveLink | ✅ active | Manual ingest from `data/xposure_urls.txt` |
| Sagicor / Sagicor Properties | ❌ dropped | AWS WAF JS challenge — needs Playwright |
| Sotheby's Jamaica | ❌ dropped | AWS WAF JS challenge — needs Playwright |
| properstar.com/jamaica | ❌ dropped | Cloudflare-tier anti-bot; not worth it |
| RE/MAX Jamaica | ❌ dropped | The .com domain is recruitment brochure, not listings |
| jamaica-homes.com | ❌ dropped | Substack newsletter, not a listings site |
| getkeez.com | ⏳ deferred | Vue SPA — would need Playwright |
| Facebook Marketplace | ⏳ deferred | Login-walled; could add manual paste-in like xposure |

## Quick start

```powershell
# Clone & install
git clone https://github.com/kwierenga/kw-7m-tracker.git
cd kw-7m-tracker
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run smoke tests
.\.venv\Scripts\python.exe -m unittest discover -s tests

# Dry run (no docs/ update)
.\.venv\Scripts\python.exe -m src.main --dry-run

# Real run (writes docs/, updates DB)
.\.venv\Scripts\python.exe -m src.main
```

The GitHub Actions workflow does the same thing every Sunday and commits the result.

## Layout

```
src/
  regions.py        Multi-region config (currently just Upton)
  models.py         RawListing + NormalizedListing
  dates.py          Jamaica dd/mm/yyyy-aware date parser
  geo.py            Haversine + parish/town centroids
  fx.py             Daily JMD/USD via open.er-api.com (cached per-day)
  store.py          SQLite + upsert + first-seen / last-seen tracking
  normalize.py      Geocode + price + type-infer + region-match + rental filter
  dedup.py          Merge close-by + close-priced listings across sources
  diff.py           Classify new / active / dropped-off
  digest.py         Jinja HTML render + write_static_site to docs/
  photos.py         First-image extraction helper for scrapers
  scrapers/
    realtor_com_intl.py
    cb_jamaica.py
    caribbean_mls.py
    millennium.py
    golden_gates.py
    century21_jm.py
    xposure_manual.py
  main.py           Orchestrator

scripts/
  inspect_sites.py  Probe sites & save HTML to data/inspect/ (one-off)

tests/
  test_parsers.py   Smoke tests for each scraper against captured fixtures
  fixtures/         Saved HTML (Mapbox tokens redacted)

data/
  listings.db       SQLite (committed weekly)
  fx_cache.json     Daily FX rates (committed)
  last_digest.html  Local preview (committed)
  inspect/          Raw scraped HTML for parser dev (gitignored)
  xposure_urls.txt  Manual-ingest URLs for xposure listings

docs/
  index.html        Latest digest (served via GitHub Pages)
  archive/          Dated snapshots of past weekly runs

.github/workflows/
  weekly.yml        Sunday cron + manual trigger
```

## Important conventions

### Date parsing — Jamaica is dd/mm/yyyy

Jamaica uses dd/mm/yyyy, NOT US mm/dd/yyyy. All ambiguous numeric date parsing goes through [`src/dates.py:parse_jamaica_date`](src/dates.py). Internally everything moves as ISO 8601 (yyyy-mm-dd) which is unambiguous. Don't add ad-hoc date parsing elsewhere.

### Anti-bot

All scrapers use `curl_cffi` with `impersonate="chrome131"` to defeat TLS-fingerprint anti-bot (Cloudflare, etc). Each scraper warms up by hitting `BASE/` once before the deeper URL — without warmup, sites occasionally return 0 cards on subsequent runs.

Sites behind **AWS WAF JavaScript challenges** (Sotheby's, Sagicor) cannot be cracked with curl_cffi — they require executing the challenge JavaScript. Adding Playwright would unlock them; deferred for now.

### Rentals are filtered out

Klaas is buying, not renting. Rentals are dropped at two layers:
1. Per-scraper, where the source HTML clearly distinguishes (millennium / golden_gates / century21_jm)
2. In `src/normalize.py:_looks_like_rental()` as a safety net (matches "for rent", "/month", etc.)

### Multi-source dedup display

When dedup merges listings from multiple sources, the digest shows the **most reputable** source's URL prominently and others as a smaller "also at" line. Source ranking is in `SOURCE_RANK` in [`src/digest.py`](src/digest.py).

### Mapbox token gotcha for fixtures

When committing saved HTML as test fixtures, GitHub push protection blocks the push because Jamaican real-estate sites embed **Mapbox public tokens** in their HTML for map widgets. Strip them before committing fixtures with a regex like `(?:pk|sk)\.[A-Za-z0-9_.\-]{40,}` → `REDACTED_TOKEN`.

## Adding a new scraper

1. Save target HTML with `scripts/inspect_sites.py` (or write an ad-hoc probe).
2. Inspect to find listing-card CSS selectors.
3. Create `src/scrapers/<name>.py` modeled on existing ones — must export `scrape() -> list[RawListing]`.
4. Add to `ALL_SCRAPERS` in `src/scrapers/__init__.py`.
5. Add `SOURCE_RANK` entry in `src/digest.py`.
6. Drop a saved fixture (Mapbox-redacted) at `tests/fixtures/<name>.html`.
7. Add a smoke test in `tests/test_parsers.py`.

## Outstanding work

- Fix Century 21 JM pagination URL pattern (currently capped at home page, ~5 cards)
- Inter-request cooldown to avoid the transient rate-limit 0-returns we see during rapid iteration
- Detail-page fetching for accurate listed-on dates (biggest accuracy gain for "new this week")
- Map view (Leaflet + OpenStreetMap) showing each listing relative to the golf course
- Price-drop tracking week-over-week
- Manual paste-in ingest for Facebook Marketplace listings (same pattern as xposure_urls.txt)
