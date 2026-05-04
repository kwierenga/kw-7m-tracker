r"""Fetch jaranks profile pages, extract external (firm) website URLs, probe them.
Ad-hoc — delete after use.
"""
from __future__ import annotations

import re
from pathlib import Path

from curl_cffi import requests as cf

OUT = Path(__file__).resolve().parent.parent / "data" / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = [
    ("sagicor",      "https://www.jaranks.com/profile/sagicor-property-services-limited"),
    ("millennium",   "https://www.jaranks.com/profile/millennium-properties-sales-and-services-limited"),
    ("c21_heaveho",  "https://www.jaranks.com/profile/century-21-heaveho-properties"),
    ("golden_gates", "https://www.jaranks.com/profile/golden-gates-realty"),
]

NOISE = (
    "googleapis", "gstatic", "google-analytics", "googletagmanager",
    "fontawesome", "jquery", "bootstrapcdn", "cdnjs", "cloudfront",
    "jsdelivr", "unpkg", "schema.org", "w3.org", "fbcdn",
    "facebook.com/tr", "twitter.com/intent",
    "linkedin.com/sharing", "linkedin.com/shareArticle",
    "youtube.com/embed", "youtu.be", "wp.com", "gravatar.com",
)

URL_RE = re.compile(r'https?://[^\s"<>\']+')


def harvest_external(html: str) -> list[str]:
    found = sorted(set(URL_RE.findall(html)))
    out = []
    for u in found:
        if "jaranks.com" in u:
            continue
        if not any(tld in u for tld in (".com", ".net", ".org", ".co.", ".jm")):
            continue
        if any(n in u for n in NOISE):
            continue
        # Strip trailing punctuation that often tags along
        u = u.rstrip(",.;:)\"'")
        out.append(u)
    # Dedupe by domain (keep first hit per host)
    seen_hosts: set[str] = set()
    final: list[str] = []
    for u in out:
        m = re.match(r"https?://([^/]+)", u)
        host = m.group(1).lower() if m else u
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        final.append(u)
    return final


def main() -> int:
    discovered: list[tuple[str, str]] = []
    with cf.Session(impersonate="chrome131") as s:
        # Phase 1: fetch profile pages
        for name, url in PROFILES:
            try:
                r = s.get(url, allow_redirects=True, timeout=20)
                (OUT / f"_jaranks_{name}.html").write_text(
                    r.text, encoding="utf-8", errors="replace"
                )
                ext = harvest_external(r.text)[:8]
                print(f"[{r.status_code}] {name}: {len(r.text)} bytes — external links:")
                for u in ext:
                    print(f"    {u}")
                # Heuristic: take the first external domain that doesn't look like
                # a generic platform (firm websites).
                for u in ext:
                    discovered.append((name, u))
            except Exception as e:  # noqa: BLE001
                print(f"[ERR] {name}: {type(e).__name__}: {e}")

        # Phase 2: probe the top-1 candidate per firm (up to 2 to be safe)
        seen_per_firm: dict[str, int] = {}
        print("\n=== probing discovered firm sites ===")
        for firm, url in discovered:
            if seen_per_firm.get(firm, 0) >= 2:
                continue
            seen_per_firm[firm] = seen_per_firm.get(firm, 0) + 1
            try:
                r = s.get(url, allow_redirects=True, timeout=20)
                fname = OUT / f"_firm_{firm}_{seen_per_firm[firm]}.html"
                fname.write_text(r.text, encoding="utf-8", errors="replace")
                print(f"[{r.status_code}] {firm}: {len(r.text):>6} bytes -> {r.url}")
            except Exception as e:  # noqa: BLE001
                print(f"[ERR] {firm} ({url}): {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
