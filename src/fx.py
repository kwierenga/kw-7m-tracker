from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx

CACHE = Path(__file__).resolve().parent.parent / "data" / "fx_cache.json"
DEFAULT_FALLBACK_JMD_PER_USD = 156.0


def get_jmd_per_usd(client: httpx.Client | None = None) -> float:
    """Return today's JMD-per-USD. Cached per-day. Falls back if API is unreachable."""
    today = date.today().isoformat()
    cache: dict[str, float] = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text())
        except Exception:  # noqa: BLE001
            cache = {}
    if today in cache:
        return cache[today]

    rate: float | None = None
    own_client = client is None
    c = client or httpx.Client(timeout=15)
    try:
        r = c.get("https://open.er-api.com/v6/latest/USD")
        r.raise_for_status()
        data = r.json()
        rate = float(data["rates"]["JMD"])
    except Exception:  # noqa: BLE001
        rate = None
    finally:
        if own_client:
            c.close()

    if rate is None:
        rate = cache.get("_last_known", DEFAULT_FALLBACK_JMD_PER_USD)
    cache[today] = rate
    cache["_last_known"] = rate
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2))
    return rate


_AMOUNT_RE = re.compile(
    r"""
    (?P<amount>[\d][\d,]*(?:\.\d+)?)             # number with thousands seps
    \s*
    (?P<suffix>M|K|million|thousand)?            # magnitude
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Currency-word detection: looked for as a substring anywhere in the price text
# (case-insensitive) BEFORE falling back to the bare-$ heuristic. This handles
# "USD $ 3,000,000" — earlier code would mis-classify those as JMD because the
# regex started parsing from the $ and never saw the leading USD.
_USD_WORDS = ("USD", "US$", "U.S.")
_JMD_WORDS = ("JMD", "JA$", "J$")


def parse_price(text: str) -> tuple[int | None, str]:
    """Parse 'US$450,000' / 'J$50M' / 'USD $ 3,000,000' / '$1.2M JMD' etc.
    Returns (usd_int, currency_label).

    currency_label is one of 'USD', 'JMD', 'unknown'. If unknown, caller should not trust.
    """
    if not text:
        return None, "unknown"
    cleaned = text.replace("\xa0", " ").strip()
    m = _AMOUNT_RE.search(cleaned)
    if not m:
        return None, "unknown"
    amount = float(m.group("amount").replace(",", ""))
    suffix = (m.group("suffix") or "").lower()
    if suffix in ("m", "million"):
        amount *= 1_000_000
    elif suffix in ("k", "thousand"):
        amount *= 1_000

    upper = cleaned.upper()
    if any(w in upper for w in _USD_WORDS):
        currency = "USD"
    elif any(w in upper for w in _JMD_WORDS):
        currency = "JMD"
    elif "$" in cleaned:
        # Bare $ with no currency word — last-resort heuristic. JA listings rarely
        # quote properties below $10K USD, and amounts above ~$1M are typically JMD
        # (a $1M+ JMD home is ~$6.4K USD). Tightened threshold from 2M to 1M to
        # better match observed data.
        currency = "JMD" if amount > 1_000_000 else "USD"
    else:
        currency = "unknown"

    if currency == "JMD":
        rate = get_jmd_per_usd()
        return int(round(amount / rate)), "JMD"
    if currency == "USD":
        return int(round(amount)), "USD"
    return None, "unknown"
