import unittest
from unittest.mock import patch

import api.index as api


class ForgeProfitTests(unittest.TestCase):
    def setUp(self):
        api._forge_market_cache = []
        api._forge_market_cache_expires_at = 0

    def tearDown(self):
        api._forge_market_cache = []
        api._forge_market_cache_expires_at = 0

    def test_bazaar_and_recursive_cost_routes_stay_separate(self):
        recipes = {
            "FINAL_ITEM": {
                "item": "FINAL_ITEM",
                "display_name": "Final Item",
                "duration": 60,
                "output_count": 1,
                "ingredients": [
                    {"item": "FORGED_PART", "amount": 2},
                    {"item": "RAW_MATERIAL", "amount": 1},
                ],
            },
            "FORGED_PART": {
                "item": "FORGED_PART",
                "display_name": "Forged Part",
                "duration": 30,
                "output_count": 1,
                "ingredients": [{"item": "RAW_MATERIAL", "amount": 3}],
            },
        }
        products = {
            "FINAL_ITEM": {
                "sell_summary": [{"pricePerUnit": 110}],
                "buy_summary": [{"pricePerUnit": 100}],
            },
            "FORGED_PART": {
                "sell_summary": [{"pricePerUnit": 40}],
                "buy_summary": [{"pricePerUnit": 35}],
            },
            "RAW_MATERIAL": {
                "sell_summary": [{"pricePerUnit": 5}],
                "buy_summary": [{"pricePerUnit": 4}],
            },
        }

        with (
            patch.dict(api.FORGE_RECIPES, recipes, clear=True),
            patch.object(api, "get_bazaar_products", return_value=products),
            patch.object(api, "get_item_metadata", return_value={}),
        ):
            item = api.build_forge_items()[0]

        self.assertEqual(item["bazaar_component_cost"], 85)
        self.assertEqual(item["recursive_forge_cost"], 35)
        self.assertEqual(item["net_revenue"], 98.75)
        self.assertEqual(item["bazaar_component_profit"], 13.75)
        self.assertEqual(item["recursive_forge_profit"], 63.75)
        self.assertEqual(item["forged_components"], ["FORGED_PART"])


if __name__ == "__main__":
    unittest.main()
