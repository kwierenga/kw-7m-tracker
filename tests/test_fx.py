"""Tests for the price parser. The currency-mix-up bug had real consequences
(a $3M USD listing showed as ~$19K and snuck past the budget filter; a CAD
$1.3M listing showed as ~$8K) — locking in the fix with explicit cases."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import fx

# Pinned for deterministic conversions:
#   1 USD = 157 JMD = 0.79 GBP = 1.37 CAD = 0.92 EUR
PINNED_RATES = {"JMD": 157.0, "GBP": 0.79, "CAD": 1.37, "EUR": 0.92}


class ParsePriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher = patch("src.fx.get_fx_rates", return_value=PINNED_RATES)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    # The bug case: "USD $ 3,000,000" must NOT be treated as JMD.
    def test_usd_with_dollar_sign_three_million(self) -> None:
        usd, label = fx.parse_price("USD $ 3,000,000")
        self.assertEqual(label, "USD")
        self.assertEqual(usd, 3_000_000)

    def test_usd_with_dollar_sign_smaller(self) -> None:
        usd, label = fx.parse_price("USD $ 875,500")
        self.assertEqual(label, "USD")
        self.assertEqual(usd, 875_500)

    def test_jmd_with_dollar_sign(self) -> None:
        usd, label = fx.parse_price("JMD $ 50,000,000")
        self.assertEqual(label, "JMD")
        self.assertEqual(usd, 318_471)

    def test_us_dollar_compact(self) -> None:
        usd, label = fx.parse_price("US$450,000")
        self.assertEqual(label, "USD")
        self.assertEqual(usd, 450_000)

    def test_jdollar_compact(self) -> None:
        usd, label = fx.parse_price("J$50M")
        self.assertEqual(label, "JMD")
        self.assertEqual(usd, 318_471)

    def test_bare_dollar_small_assumed_usd(self) -> None:
        usd, label = fx.parse_price("$ 500,000")
        self.assertEqual(label, "USD")
        self.assertEqual(usd, 500_000)

    def test_bare_dollar_large_assumed_jmd(self) -> None:
        usd, label = fx.parse_price("$ 50,000,000")
        self.assertEqual(label, "JMD")
        self.assertEqual(usd, 318_471)

    def test_unparseable(self) -> None:
        usd, label = fx.parse_price("Price Available Upon Request")
        self.assertIsNone(usd)
        self.assertEqual(label, "unknown")

    def test_empty(self) -> None:
        usd, label = fx.parse_price("")
        self.assertIsNone(usd)
        self.assertEqual(label, "unknown")

    # --- new: GBP / CAD / EUR detection ---

    def test_gbp_word(self) -> None:
        # The exact bug from the live DB: 'GBP\n  $430,000' was being
        # classified as USD because GBP wasn't a known currency word.
        usd, label = fx.parse_price("GBP\n                                $430,000")
        self.assertEqual(label, "GBP")
        # 430,000 / 0.79 = 544,303.79...
        self.assertEqual(usd, 544_304)

    def test_gbp_pound_symbol(self) -> None:
        usd, label = fx.parse_price("£500,000")
        self.assertEqual(label, "GBP")
        self.assertEqual(usd, 632_911)

    def test_cad_word_mount_boon_case(self) -> None:
        # The exact bug: 'CAD\n  $1,300,000' was misclassified JMD because
        # CAD wasn't a known currency word, then bare-$ heuristic saw >1M
        # and decided JMD — collapsing the price to ~$8K.
        usd, label = fx.parse_price("CAD\n                                $1,300,000")
        self.assertEqual(label, "CAD")
        # 1,300,000 / 1.37 = 948,905.10...
        self.assertEqual(usd, 948_905)

    def test_cad_compact_c_dollar(self) -> None:
        usd, label = fx.parse_price("C$1,300,000")
        self.assertEqual(label, "CAD")
        self.assertEqual(usd, 948_905)

    def test_eur_word(self) -> None:
        usd, label = fx.parse_price("EUR 500,000")
        self.assertEqual(label, "EUR")
        # 500,000 / 0.92 = 543,478.26...
        self.assertEqual(usd, 543_478)

    def test_eur_symbol(self) -> None:
        usd, label = fx.parse_price("€500,000")
        self.assertEqual(label, "EUR")
        self.assertEqual(usd, 543_478)


class GetFxRatesCacheTests(unittest.TestCase):
    """The cache-format migration matters because the on-disk cache from
    earlier versions is a {date: float, _last_known: float} shape. The new
    code expects {date: dict, _last_known: dict} — old entries should be
    treated as a missing-cache (refetch) without crashing or returning a
    bare float."""

    def test_old_format_cache_is_handled_in_fallback(self) -> None:
        # Direct unit test of _fallback_rates: old _last_known is a float,
        # should upgrade to the full default dict with that JMD rate.
        cache = {"_last_known": 158.5}
        rates = fx._fallback_rates(cache)
        self.assertEqual(rates["JMD"], 158.5)
        # The other currencies fall back to defaults.
        self.assertEqual(rates["GBP"], fx.DEFAULT_FALLBACK_RATES["GBP"])
        self.assertEqual(rates["CAD"], fx.DEFAULT_FALLBACK_RATES["CAD"])
        self.assertEqual(rates["EUR"], fx.DEFAULT_FALLBACK_RATES["EUR"])

    def test_no_cache_falls_back_to_defaults(self) -> None:
        rates = fx._fallback_rates({})
        self.assertEqual(rates, fx.DEFAULT_FALLBACK_RATES)

    def test_full_dict_last_known_is_used_directly(self) -> None:
        cache = {"_last_known": {"JMD": 160.0, "GBP": 0.80, "CAD": 1.38, "EUR": 0.93}}
        rates = fx._fallback_rates(cache)
        self.assertEqual(rates, {"JMD": 160.0, "GBP": 0.80, "CAD": 1.38, "EUR": 0.93})


if __name__ == "__main__":
    unittest.main()
