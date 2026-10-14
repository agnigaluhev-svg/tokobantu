"""Test script to verify Shopify GraphQL connection.

Queries the first 5 products from the store and prints their title and total inventory.
"""

from app.shopify_client import graphql

PRODUCTS_QUERY = """
query GetFirstFiveProducts {
  products(first: 5) {
    nodes {
      title
      totalInventory
    }
  }
}
"""


def main() -> None:
    """Fetch and display the first 5 products from Shopify."""
    print("Fetching first 5 products from Shopify...")
    try:
        data = graphql(PRODUCTS_QUERY)
    except Exception as exc:
        print(f"Error executing GraphQL query: {exc}")
        return

    products = data.get("products", {}).get("nodes", [])

    if not products:
        print("No products found in the store.")
        return

    print(f"Retrieved {len(products)} product(s):\n")
    for index, product in enumerate(products, start=1):
        title = product.get("title", "Untitled")
        stock = product.get("totalInventory", 0)
        print(f"{index}. Title: {title} | Total Inventory: {stock}")


if __name__ == "__main__":
    main()
