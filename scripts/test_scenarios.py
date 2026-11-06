"""Deterministic offline checks for important store support scenarios."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "true"

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.tools import orders, products


class StoreScenarioTests(unittest.TestCase):
    """Verify tool outcomes from controlled Shopify GraphQL responses."""

    def test_tracked_product_with_quantity_is_in_stock(self) -> None:
        """Report available stock when inventory is tracked and positive."""
        response = {
            "product": {
                "title": "Snowboard",
                "tracksInventory": True,
                "totalInventory": 4,
                "variants": {"nodes": [{"title": "Blue", "inventoryQuantity": 4}]},
            }
        }
        with patch.object(products, "graphql", return_value=response):
            result = products.get_stock("123")
        self.assertEqual(result["stock_status"], "in_stock")
        self.assertEqual(result["variants"][0]["stock"], 4)

    def test_tracked_product_with_zero_quantity_is_out_of_stock(self) -> None:
        """Report sold out only for tracked inventory with no quantity."""
        response = {
            "product": {
                "title": "Snowboard",
                "tracksInventory": True,
                "totalInventory": 0,
                "variants": {"nodes": [{"title": "Blue", "inventoryQuantity": 0}]},
            }
        }
        with patch.object(products, "graphql", return_value=response):
            result = products.get_stock("123")
        self.assertEqual(result["stock_status"], "out_of_stock")
        self.assertEqual(result["variants"][0]["stock"], 0)

    def test_untracked_product_is_not_reported_as_sold_out(self) -> None:
        """Preserve unknown stock as not_tracked and hide a false zero."""
        response = {
            "product": {
                "title": "Custom item",
                "tracksInventory": False,
                "totalInventory": 0,
                "variants": {"nodes": [{"title": "Default", "inventoryQuantity": 0}]},
            }
        }
        with patch.object(products, "graphql", return_value=response):
            result = products.get_stock("123")
        self.assertEqual(result["stock_status"], "not_tracked")
        self.assertIsNone(result["variants"][0]["stock"])

    @staticmethod
    def verified_order(email: str = "buyer@example.com") -> dict[str, object]:
        """Build a representative Shopify order response for offline checks."""
        return {
            "orders": {
                "nodes": [{
                    "name": "#1001",
                    "createdAt": "2026-10-20T10:00:00Z",
                    "displayFinancialStatus": "PAID",
                    "displayFulfillmentStatus": "FULFILLED",
                    "cancelledAt": None,
                    "email": email,
                    "phone": "+628123456789",
                    "shippingAddress": {"address1": "Private address"},
                    "totalPriceSet": {"shopMoney": {"amount": "99.00", "currencyCode": "USD"}},
                    "lineItems": {"nodes": [{"title": "Snowboard", "quantity": 1}]},
                    "fulfillments": [{"trackingInfo": [{"company": "Courier", "number": "TRACK-1", "url": "https://example.test/track"}]}],
                }]
            }
        }

    def test_verified_order_returns_status_without_personal_details(self) -> None:
        """Return order facts while excluding address and phone fields."""
        with patch.object(orders, "graphql", return_value=self.verified_order()):
            result = orders.get_order_status("#1001", "BUYER@example.com")
        self.assertTrue(result["verified"])
        self.assertEqual(result["payment_status"], "PAID")
        self.assertEqual(result["items"], [{"title": "Snowboard", "quantity": 1}])
        self.assertEqual(result["tracking"][0]["number"], "TRACK-1")
        self.assertNotIn("email", result)
        self.assertNotIn("phone", result)
        self.assertNotIn("shippingAddress", result)

    def test_wrong_email_and_missing_order_have_identical_reply(self) -> None:
        """Avoid revealing whether an order exists when verification fails."""
        with patch.object(
            orders,
            "graphql",
            side_effect=[self.verified_order(), {"orders": {"nodes": []}}],
        ):
            wrong_email = orders.get_order_status("#1001", "other@example.com")
            missing_order = orders.get_order_status("#9999", "buyer@example.com")
        self.assertEqual(wrong_email, missing_order)

    def test_injection_order_number_is_rejected_without_shopify_call(self) -> None:
        """Reject malformed order numbers before they reach Shopify GraphQL."""
        with patch.object(orders, "graphql") as graphql_mock:
            result = orders.get_order_status("1001 OR 1", "buyer@example.com")
        self.assertEqual(result["verified"], False)
        graphql_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
