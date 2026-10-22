"""Test script to verify product search and inventory stock tools.

Tests searching for products ('snowboard', 'gift', 'xyz-tidak-ada'),
checks stock levels for a tracked snowboard product,
and checks stock levels for 'The Inventory Not Tracked Snowboard'.
Does not print any API tokens or sensitive credentials.
"""

from app.tools.products import get_stock, search_products


def main() -> None:
    """Run verification tests for search_products and get_stock."""
    print("=== Test 1: search_products('snowboard') ===")
    snowboard_res = search_products("snowboard")
    if not snowboard_res.get("ok"):
        print(f"Error: {snowboard_res.get('error')}")
        snowboards = []
    else:
        snowboards = snowboard_res.get("results", [])
        print(f"Total found: {len(snowboards)}")
        for item in snowboards:
            print(
                f"  ID: {item['id']} | Title: {item['title']} | "
                f"Status: {item['status']} | Price: {item['min_price']} {item['currency']} | "
                f"Stock: {item['stock_status']}"
            )
    print()

    print("=== Test 2: search_products('gift') ===")
    gift_res = search_products("gift")
    if not gift_res.get("ok"):
        print(f"Error: {gift_res.get('error')}")
    else:
        gifts = gift_res.get("results", [])
        print(f"Total found: {len(gifts)}")
        for item in gifts:
            print(
                f"  ID: {item['id']} | Title: {item['title']} | "
                f"Status: {item['status']} | Price: {item['min_price']} {item['currency']} | "
                f"Stock: {item['stock_status']}"
            )
    print()

    print("=== Test 3: search_products('xyz-tidak-ada') ===")
    empty_res = search_products("xyz-tidak-ada")
    if not empty_res.get("ok"):
        print(f"Error: {empty_res.get('error')}")
    else:
        empty_results = empty_res.get("results", [])
        print(f"Total found: {len(empty_results)} (expected 0)")
    print()

    print("=== Test 4: get_stock for the first snowboard product ===")
    if snowboards:
        target_product = snowboards[0]
        target_id = target_product["id"]
        print(f"Checking stock for: {target_product['title']} (ID: {target_id})")

        stock_data = get_stock(target_id)
        if not stock_data.get("ok"):
            print(f"Error: {stock_data.get('error')}")
        elif not stock_data.get("found"):
            print("Product not found.")
        else:
            print(f"Title: {stock_data.get('title')}")
            print(f"Stock Status: {stock_data.get('stock_status')}")
            print("Variants:")
            for variant in stock_data.get("variants", []):
                print(f"  - {variant.get('name')}: {variant.get('stock')} pcs")
    else:
        print("No snowboard product available to run get_stock test.")
    print()

    print("=== Test 5: get_stock for 'The Inventory Not Tracked Snowboard' ===")
    not_tracked_search = search_products("The Inventory Not Tracked Snowboard")
    if not not_tracked_search.get("ok"):
        print(f"Error searching product: {not_tracked_search.get('error')}")
    else:
        not_tracked_products = not_tracked_search.get("results", [])
        if not_tracked_products:
            not_tracked_id = not_tracked_products[0]["id"]
            print(f"Found product ID: {not_tracked_id}. Checking stock...")
            stock_data = get_stock(not_tracked_id)
            if not stock_data.get("ok"):
                print(f"Error: {stock_data.get('error')}")
            elif not stock_data.get("found"):
                print("Product not found.")
            else:
                print(f"Title: {stock_data.get('title')}")
                print(f"Stock Status: {stock_data.get('stock_status')}")
                print("Variants:")
                for variant in stock_data.get("variants", []):
                    print(f"  - {variant.get('name')}: stock={variant.get('stock')}")
        else:
            print("Product 'The Inventory Not Tracked Snowboard' not found in catalog.")


if __name__ == "__main__":
    main()
