r"""One-off probe: fetch candidate listing pages and save raw HTML for inspection.

Run: .venv/Scripts/python.exe scripts/inspect_sites.py
Output: data/inspect/<site>__<label>.html

Uses curl_cffi with Chrome TLS fingerprint impersonation. This defeats most
modern anti-bot (Cloudflare, Akamai etc.) by making the TCP/TLS handshake
look like real Chrome rather than a Python HTTP client.

Sessions are reused per host so cookies (e.g. CF clearance) carry across
the warm-up + deep-link requests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as cf

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

IMPERSONATE = "chrome131"

TARGETS: list[tuple[str, str, str]] = [
    ("realtor_com_intl", "jamaica", "https://www.realtor.com/international/jm/"),
    # KW: try several paths since franchise subdomains often hide listings under a non-root URL.
    ("kw_jamaica", "home", "https://kellerwilliamsjamaica.kw.com/"),
    ("kw_jamaica", "listings", "https://kellerwilliamsjamaica.kw.com/listings"),
    ("kw_jamaica", "listing_all", "https://kellerwilliamsjamaica.kw.com/listing/all"),
    ("kw_jamaica", "properties", "https://kellerwilliamsjamaica.kw.com/properties"),
    ("keez", "home", "https://www.getkeez.com/"),
    ("cb_jamaica", "home", "https://cbjamaica.com/"),
    ("properstar", "buy_jamaica", "https://www.properstar.com/jamaica/buy"),
    ("jamaica_homes", "home", "https://www.jamaica-homes.com/"),
    ("caribbean_mls", "jamaica", "https://caribbeanrealestatemls.com/destinations/jamaica/"),
]


def main() -> int:
    sessions: dict[str, cf.Session] = {}
    warmed: set[str] = set()
    failures = 0
    try:
        for site, label, url in TARGETS:
            host = urlparse(url).netloc
            if host not in sessions:
                sessions[host] = cf.Session(impersonate=IMPERSONATE)
            session = sessions[host]

            if host not in warmed:
                try:
                    session.get(f"https://{host}/", allow_redirects=True, timeout=30)
                except Exception:  # noqa: BLE001
                    pass
                warmed.add(host)

            try:
                r = session.get(url, allow_redirects=True, timeout=30)
                size = len(r.text)
                fname = OUT / f"{site}__{label}.html"
                fname.write_text(r.text, encoding="utf-8", errors="replace")
                print(f"[{r.status_code}] {site}/{label}: {size:>7} bytes -> {r.url}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"[ERR] {site}/{label}: {type(e).__name__}: {e}")
    finally:
        for s in sessions.values():
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
    if failures:
        print(f"\n{failures} failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
