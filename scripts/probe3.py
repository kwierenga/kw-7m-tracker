r"""Quick probe of 3 firm sites Klaas just provided. Throwaway."""
from __future__ import annotations

from pathlib import Path

from curl_cffi import requests as cf

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

URLS = [
    ("sagicor_ja",     "https://www.sagicor.com/en-jm/personal-solution/real-estate"),
    ("millennium",     "https://www.millenniumpropertiessalesandservices.com/"),
    ("century21_jm",   "https://century21jm.com/"),
]

LISTING_KW = ("listing", "property", "price", "bedroom", "usd", "jmd", "us$", "j$")
SPA_MARK = ("__next_data__", "window.__", "apollo_state", "<app-root", "ng-app", "ember-application", "v-cloak")


def main() -> int:
    with cf.Session(impersonate="chrome131") as s:
        for name, url in URLS:
            try:
                r = s.get(url, allow_redirects=True, timeout=25)
                (OUT / f"_{name}__home.html").write_text(r.text, encoding="utf-8", errors="replace")
                txt = r.text.lower()
                listing_hits = sum(txt.count(w) for w in LISTING_KW)
                spa_hits = sum(txt.count(w) for w in SPA_MARK)
                print(f"[{r.status_code}] {name:14s} {len(r.text):>7} bytes  listings:{listing_hits:>3}  spa:{spa_hits:>2}  -> {r.url}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERR] {name}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
