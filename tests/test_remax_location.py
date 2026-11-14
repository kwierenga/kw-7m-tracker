import unittest

from src.scrapers.remax_elite import _location_with_town, _town_from_url

BASE = "https://remax-elite.com.jm/property/"


class RemaxLocationTests(unittest.TestCase):
    def test_town_is_taken_from_the_url_slug(self) -> None:
        self.assertEqual(_town_from_url(BASE + "St-dot-+Ann++Runaway+Bay/MLS-8721"), "Runaway Bay")
        self.assertEqual(_town_from_url(BASE + "Kingston+-and-+St-dot-+Andrew++Kingston+4/MLS-1"), "Kingston 4")
        self.assertIsNone(_town_from_url(BASE + "Westmoreland/MLS-2"))  # parish only
        self.assertIsNone(_town_from_url("https://remax-elite.com.jm/about"))

    def test_town_is_inserted_before_the_parish(self) -> None:
        self.assertEqual(
            _location_with_town("Cardiff Hall Plantation , St. Ann", BASE + "St-dot-+Ann++Runaway+Bay/MLS-8721"),
            "Cardiff Hall Plantation, Runaway Bay, St. Ann",
        )

    def test_town_already_present_is_not_repeated(self) -> None:
        self.assertEqual(
            _location_with_town("Bridgewater, Discovery Bay , St. Ann", BASE + "St-dot-+Ann++Discovery+Bay/MLS-9"),
            "Bridgewater, Discovery Bay, St. Ann",
        )

    def test_truncated_district_is_replaced_by_the_town(self) -> None:
        self.assertEqual(
            _location_with_town("Bridgewater, Discovery Ba , St. Ann", BASE + "St-dot-+Ann++Discovery+Bay/MLS-9"),
            "Bridgewater, Discovery Bay, St. Ann",
        )

    def test_missing_pieces(self) -> None:
        self.assertEqual(_location_with_town(None, BASE + "St-dot-+Ann++Ocho+Rios/RME-5"), "Ocho Rios")
        self.assertEqual(_location_with_town("Westmoreland , Westmoreland", BASE + "Westmoreland/MLS-2"), "Westmoreland, Westmoreland")


if __name__ == "__main__":
    unittest.main()
