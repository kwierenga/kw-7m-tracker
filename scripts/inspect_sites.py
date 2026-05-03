r"""One-off probe: fetch candidate listing pages and save raw HTML for inspection.

Run: .venv/Scripts/python.exe scripts/inspect_sites.py
Output: data/inspect/<site>__<label>.html

Uses a session with full browser-like headers to defeat basic bot blocks.
For each (site, ...) the session is reused, so cookies set by earlier requests
to the same host (e.g. Cloudflare clearance) carry forward.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

TARGETS: list[tuple[str, str, str]] = [
    ("realtor_com_intl", "jamaica", "https://www.realtor.com/international/jm/"),
    # KW: try several paths since franchise subdomains often hide listings under a non-root URL.
    ("kw_jamaica", "home", "https://kellerwilliamsjamaica.kw.com/"),
    ("kw_jamaica", "listings", "https://kellerwilliamsjamaica.kw.com/listings"),
    ("kw_jamaica", "listing_all", "https://kellerwilliamsjamaica.kw.com/listing/all"),
    ("kw_jamaica", "properties", "https://kellerwilliamsjamaica.kw.com/properties"),
    ("keez", "home", "https://www.getkeez.com/"),
    ("xposure", "home", "https://jamaica.xposureapp.com/"),
    ("cb_jamaica", "home", "https://cbjamaica.com/"),
    ("properstar", "buy_jamaica", "https://www.properstar.com/jamaica/buy"),
    ("jamaica_homes", "home", "https://www.jamaica-homes.com/"),
    ("caribbean_mls", "jamaica", "https://caribbeanrealestatemls.com/destinations/jamaica/"),
]


def main() -> int:
    failures: list[tuple[str, str, str]] = []
    sessions: dict[str, httpx.Client] = {}
    warmed: set[str] = set()
    try:
        for site, label, url in TARGETS:
            host = urlparse(url).netloc
            if host not in sessions:
                sessions[host] = httpx.Client(
                    headers=HEADERS, follow_redirects=True, timeout=30, http2=False
                )
            client = sessions[host]
            if host not in warmed:
                # Warm the session: hit the root once so the host can drop session cookies
                # before we ask for a deeper URL. Some bot blockers require this.
                root = f"{urlparse(url).scheme}://{host}/"
                try:
                    client.get(root)
                except httpx.HTTPError:
                    pass
                warmed.add(host)
            try:
                # On subsequent requests to same host, set Sec-Fetch-Site to same-origin.
                req_headers = {} if host not in warmed else {"Sec-Fetch-Site": "same-origin"}
                r = client.get(url, headers=req_headers)
                final = str(r.url)
                size = len(r.text)
                fname = OUT / f"{site}__{label}.html"
                fname.write_text(r.text, encoding="utf-8", errors="replace")
                print(f"[{r.status_code}] {site}/{label}: {size:>7} bytes -> {final}")
            except Exception as e:  # noqa: BLE001
                failures.append((site, label, f"{type(e).__name__}: {e}"))
                print(f"[ERR] {site}/{label}: {type(e).__name__}: {e}")
    finally:
        for c in sessions.values():
            c.close()
    if failures:
        print(f"\n{len(failures)} failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
