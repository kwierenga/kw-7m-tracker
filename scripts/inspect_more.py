r"""Ad-hoc probe of additional Jamaican real-estate sites suggested by Klaas.
Not intended to be committed/maintained — once we know which URLs are real,
the survivors get added to scraper modules and this file can be deleted.
"""
from __future__ import annotations

from pathlib import Path

from curl_cffi import requests as cf

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

CANDIDATES: list[tuple[str, str]] = [
    ("sagicor",                  "https://www.sagicorpropertyservices.com/"),
    ("sagicor_alt",              "https://sagicorpropertyservices.com/"),
    ("sagicor_parent",           "https://www.sagicor.com/"),
    ("millennium",               "https://www.millenniumpropertiesja.com/"),
    ("millennium_alt1",          "https://millenniumpropertiesjamaica.com/"),
    ("millennium_alt2",          "https://millenniumproperties.com.jm/"),
    ("century21_ja",             "https://www.century21jamaica.com/"),
    ("c21_heaveho",              "https://www.c21heaveho.com/"),
    ("heaveho",                  "https://www.heavehoproperties.com/"),
    ("golden_gates",             "https://www.goldengatesrealty.com/"),
    ("golden_gates_alt",         "https://goldengatesrealty.com/"),
    # Bonus probes from the earlier suggestion list:
    ("remax_jamaica",            "https://www.remax-jamaica.com/"),
    ("terra_caribbean_jamaica",  "https://www.terracaribbean.com/jamaica/"),
    ("seventh_heaven",           "https://www.7thheavenproperties.com/jamaica-property/"),
]


def main() -> int:
    with cf.Session(impersonate="chrome131") as s:
        for site, url in CANDIDATES:
            try:
                r = s.get(url, allow_redirects=True, timeout=20)
                fname = OUT / f"_{site}__home.html"
                fname.write_text(r.text, encoding="utf-8", errors="replace")
                print(f"[{r.status_code}] {site:30s} {len(r.text):>7} bytes -> {r.url}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERR] {site:30s} {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
