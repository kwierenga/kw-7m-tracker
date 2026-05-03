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


_PRICE_RE = re.compile(
    r"""
    (?P<currency>USD?|US\$|J\$|JMD|JA\$|\$)?     # optional leading currency
    \s*
    (?P<amount>[\d][\d,]*(?:\.\d+)?)             # number with thousands seps
    \s*
    (?P<suffix>M|K|million|thousand)?            # magnitude
    \s*
    (?P<currency2>USD?|JMD|US\$|J\$|JA\$)?        # optional trailing
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_price(text: str) -> tuple[int | None, str]:
    """Parse 'US$450,000' / 'J$50M' / '$1.2M USD' etc. Returns (usd_int, currency_label).

    currency_label is one of 'USD', 'JMD', 'unknown'. If unknown, caller should not trust.
    """
    if not text:
        return None, "unknown"
    cleaned = text.replace("\xa0", " ").strip()
    m = _PRICE_RE.search(cleaned)
    if not m:
        return None, "unknown"
    amount = float(m.group("amount").replace(",", ""))
    suffix = (m.group("suffix") or "").lower()
    if suffix in ("m", "million"):
        amount *= 1_000_000
    elif suffix in ("k", "thousand"):
        amount *= 1_000

    cur_raw = (m.group("currency") or m.group("currency2") or "").upper().replace(" ", "")
    if cur_raw in ("US$", "USD"):
        currency = "USD"
    elif cur_raw in ("J$", "JMD", "JA$"):
        currency = "JMD"
    elif cur_raw == "$":
        # Bare $ is ambiguous in JA listings. Heuristic: under 10,000 likely USD/k typo,
        # 10,000-2,000,000 likely USD, > 2,000,000 likely JMD.
        if amount > 2_000_000:
            currency = "JMD"
        else:
            currency = "USD"
    else:
        currency = "unknown"

    if currency == "JMD":
        rate = get_jmd_per_usd()
        return int(round(amount / rate)), "JMD"
    if currency == "USD":
        return int(round(amount)), "USD"
    return None, "unknown"
