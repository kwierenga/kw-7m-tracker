"""One-off probe: fetch candidate listing pages and save raw HTML for inspection.

Run: .venv\Scripts\python.exe scripts\inspect_sites.py
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
    ("realtor_jamaica", "home", "https://www.realtorjamaica.com/"),
    ("realtor_jamaica", "search_st_ann", "https://www.realtorjamaica.com/property/?parishes=st-ann"),
    ("propertyads", "home", "https://propertyads.com.jm/"),
    ("propertyads", "search_st_ann", "https://propertyads.com.jm/?location=st-ann"),
    ("caribbean_property", "home", "https://www.caribbeanpropertylistings.com/"),
    ("caribbean_property", "search_jamaica_ocho_rios", "https://www.caribbeanpropertylistings.com/listings/?country=jamaica&city=ocho-rios"),
    ("century21_ja", "home", "https://www.century21jamaica.com/"),
    ("coldwell_ja", "home", "https://www.coldwellbankerjamaica.com/"),
    ("kw_ja", "home", "https://www.kwjamaica.com/"),
    ("gleaner_classifieds", "home", "https://classifieds.jamaica-gleaner.com/"),
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
