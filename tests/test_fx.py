"""Tests for the price parser. The currency-mix-up bug had real consequences
(a $3M USD listing showed as ~$19K and snuck past the budget filter) — locking
in the fix with explicit cases."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import fx


class ParsePriceTests(unittest.TestCase):
    def setUp(self) -> None:
        # Pin the FX rate so the test is deterministic.
        self._patcher = patch("src.fx.get_jmd_per_usd", return_value=157.0)
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
        # 50,000,000 / 157.0 = 318471.337...
        self.assertEqual(usd, 318_471)

    def test_us_dollar_compact(self) -> None:
        usd, label = fx.parse_price("US$450,000")
        self.assertEqual(label, "USD")
        self.assertEqual(usd, 450_000)

    def test_jdollar_compact(self) -> None:
        usd, label = fx.parse_price("J$50M")
        self.assertEqual(label, "JMD")
        # 50,000,000 / 157.0 = 318471
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


if __name__ == "__main__":
    unittest.main()
