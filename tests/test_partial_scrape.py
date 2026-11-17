import unittest

from src.main import partial_sources


class PartialScrapeTests(unittest.TestCase):
    def test_collapsed_count_is_flagged(self) -> None:
        self.assertEqual(partial_sources({"remax_elite": 300, "keez": 1300}, {"remax_elite": 1700, "keez": 1350}), ["remax_elite"])

    def test_failed_first_run_and_growth_are_not_flagged(self) -> None:
        self.assertEqual(partial_sources({"a": -1, "b": 10, "c": 900}, {"a": 500, "c": 600}), [])
        self.assertEqual(partial_sources({"a": 10}, {"a": -1}), [])


if __name__ == "__main__":
    unittest.main()
