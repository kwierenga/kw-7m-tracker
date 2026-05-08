from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx

CACHE = Path(__file__).resolve().parent.parent / "data" / "fx_cache.json"

# Foreign currencies we recognize on listings, with conservative fallback
# rates (units per USD) used when the FX API is unreachable. Real rates are
# fetched on first call per day; fallbacks just keep the parser working
# offline rather than silently mis-classifying.
FOREIGN_CURRENCIES = ("JMD", "GBP", "CAD", "EUR")
DEFAULT_FALLBACK_RATES: dict[str, float] = {
    "JMD": 156.0,
    "GBP": 0.79,
    "CAD": 1.37,
    "EUR": 0.92,
}
DEFAULT_FALLBACK_JMD_PER_USD = DEFAULT_FALLBACK_RATES["JMD"]


def _read_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        return json.loads(CACHE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _write_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2))


def _fallback_rates(cache: dict) -> dict[str, float]:
    """Best-effort rates when the FX API is unreachable. Prefer last-known
    full set, then upgrade an old-format float (legacy: JMD-only rate) to
    a full dict, then bake in the static defaults."""
    last = cache.get("_last_known")
    if isinstance(last, dict) and all(c in last for c in FOREIGN_CURRENCIES):
        return {c: float(last[c]) for c in FOREIGN_CURRENCIES}
    base = dict(DEFAULT_FALLBACK_RATES)
    if isinstance(last, dict):
        for c, v in last.items():
            if c in FOREIGN_CURRENCIES:
                base[c] = float(v)
    elif isinstance(last, (int, float)):
        base["JMD"] = float(last)
    return base


def get_fx_rates(client: httpx.Client | None = None) -> dict[str, float]:
    """Returns {currency: units_per_usd} for FOREIGN_CURRENCIES. Cached per
    day in data/fx_cache.json. Falls back through last-known then static
    defaults when the FX API is unreachable."""
    today = date.today().isoformat()
    cache = _read_cache()
    cached = cache.get(today)
    if isinstance(cached, dict) and all(c in cached for c in FOREIGN_CURRENCIES):
        return {c: float(cached[c]) for c in FOREIGN_CURRENCIES}

    rates: dict[str, float] | None = None
    own_client = client is None
    c = client or httpx.Client(timeout=15)
    try:
        r = c.get("https://open.er-api.com/v6/latest/USD")
        r.raise_for_status()
        data = r.json()
        api_rates = data.get("rates", {})
        candidate = {cur: float(api_rates[cur]) for cur in FOREIGN_CURRENCIES if cur in api_rates}
        if len(candidate) == len(FOREIGN_CURRENCIES):
            rates = candidate
    except Exception:  # noqa: BLE001
        rates = None
    finally:
        if own_client:
            c.close()

    if rates is None:
        rates = _fallback_rates(cache)

    cache[today] = rates
    cache["_last_known"] = rates
    _write_cache(cache)
    return rates


def get_jmd_per_usd(client: httpx.Client | None = None) -> float:
    """Backward-compatible wrapper for callers that only need the JMD rate
    (the per-run print line in main.py and one or two older call sites)."""
    return get_fx_rates(client).get("JMD", DEFAULT_FALLBACK_JMD_PER_USD)


_AMOUNT_RE = re.compile(
    r"""
    (?P<amount>[\d][\d,]*(?:\.\d+)?)             # number with thousands seps
    \s*
    (?P<suffix>M|K|million|thousand)?            # magnitude
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Currency-word detection: looked for as a substring anywhere in the price text
# (case-insensitive) BEFORE falling back to the bare-$ heuristic. Order is
# significant only when one code's word is a substring of another's; the
# current set has no such overlaps. £ and € are kept literal — .upper()
# preserves them so the substring check still works.
_CURRENCY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("USD", ("USD", "US$", "U.S.", "U.S$")),
    ("JMD", ("JMD", "JA$", "J$")),
    ("GBP", ("GBP", "£", "POUND", "STERLING")),
    ("CAD", ("CAD", "C$", "CA$", "CDN")),
    ("EUR", ("EUR", "€", "EURO")),
)


def _detect_currency(cleaned: str) -> str:
    upper = cleaned.upper()
    for code, words in _CURRENCY_WORDS:
        if any(w in upper for w in words):
            return code
    return "unknown"


def parse_price(text: str) -> tuple[int | None, str]:
    """Parse a listing's raw price string. Returns (price_in_usd, currency_label)
    where currency_label is one of 'USD', 'JMD', 'GBP', 'CAD', 'EUR', 'unknown'.

    A non-USD currency triggers a get_fx_rates() call to convert to USD; the
    returned int is always USD regardless of source currency. Caller should
    keep the original price string around to show 'was {original}' for
    non-USD listings."""
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

    currency = _detect_currency(cleaned)
    if currency == "unknown" and "$" in cleaned:
        # Last-resort heuristic for bare "$" with no currency word at all.
        # JA listings rarely quote properties below ~$10K USD, and amounts
        # above ~$1M are typically JMD (a $1M+ JMD home is ~$6.4K USD).
        # With GBP/CAD/EUR detection wired up above, this only fires when
        # NONE of the currency words are present in the string.
        currency = "JMD" if amount > 1_000_000 else "USD"

    if currency == "USD":
        return int(round(amount)), "USD"
    if currency == "unknown":
        return None, "unknown"

    rates = get_fx_rates()
    rate = rates.get(currency)
    if not rate:
        return None, currency
    return int(round(amount / rate)), currency
