"""Debug script to inspect recent orders in Shopify development store.

Retrieves the 10 most recent orders using graphql() from app.shopify_client
with fields: name, email, displayFinancialStatus, displayFulfillmentStatus, cancelledAt.
Prints each order on a single line and prints raw GraphQL errors if encountered.
Does not print any API tokens or credentials.
"""

import sys
from pathlib import Path

# Add project root to sys.path so app can be imported when running standalone
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.shopify_client import graphql

RECENT_ORDERS_QUERY = """
query GetRecentOrders {
  orders(first: 10, sortKey: CREATED_AT, reverse: true) {
    nodes {
      name
      email
      displayFinancialStatus
      displayFulfillmentStatus
      cancelledAt
    }
  }
}
"""


def main() -> None:
    """Fetch and print the 10 most recent orders or output raw error."""
    try:
        data = graphql(RECENT_ORDERS_QUERY)
    except Exception as exc:
        print(f"Error: {exc}")
        return

    orders = data.get("orders", {}).get("nodes", [])
    if not orders:
        print("Tidak ada pesanan ditemukan.")
        return

    for order in orders:
        name = order.get("name")
        email = order.get("email")
        financial = order.get("displayFinancialStatus")
        fulfillment = order.get("displayFulfillmentStatus")
        cancelled = order.get("cancelledAt")
        print(
            f"Name: {name} | "
            f"Email: {email} | "
            f"Financial: {financial} | "
            f"Fulfillment: {fulfillment} | "
            f"CancelledAt: {cancelled}"
        )


if __name__ == "__main__":
    main()
