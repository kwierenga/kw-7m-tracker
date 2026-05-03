r"""One-off probe: fetch candidate listing pages and save raw HTML for inspection.

Run: .venv/Scripts/python.exe scripts/inspect_sites.py
Output: data/inspect/<site>__<label>.html
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TARGETS: list[tuple[str, str, str]] = [
    ("realtor_com_intl", "jamaica", "https://www.realtor.com/international/jm/"),
    ("kw_jamaica", "home", "https://kellerwilliamsjamaica.kw.com/"),
    ("keez", "home", "https://www.getkeez.com/"),
    ("xposure", "home", "https://jamaica.xposureapp.com/"),
    ("cb_jamaica", "home", "https://cbjamaica.com/"),
    ("properstar", "buy_jamaica", "https://www.properstar.com/jamaica/buy"),
    ("jamaica_homes", "home", "https://www.jamaica-homes.com/"),
    ("caribbean_mls", "jamaica", "https://caribbeanrealestatemls.com/destinations/jamaica/"),
]


def main() -> int:
    failures: list[tuple[str, str, str]] = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=20) as client:
        for site, label, url in TARGETS:
            try:
                r = client.get(url)
                final = str(r.url)
                size = len(r.text)
                fname = OUT / f"{site}__{label}.html"
                fname.write_text(r.text, encoding="utf-8", errors="replace")
                print(f"[{r.status_code}] {site}/{label}: {size:>7} bytes -> {final}")
            except Exception as e:  # noqa: BLE001
                failures.append((site, label, f"{type(e).__name__}: {e}"))
                print(f"[ERR] {site}/{label}: {type(e).__name__}: {e}")
    if failures:
        print(f"\n{len(failures)} failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
