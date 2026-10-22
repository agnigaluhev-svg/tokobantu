"""Product search and inventory management tools for TokoBantu.

Provides functions to search products and inspect variant stock levels
using the Shopify GraphQL Admin API.
"""

import re
from typing import Any
from app.shopify_client import graphql

SEARCH_PRODUCTS_QUERY = """
query SearchProducts($query: String!, $first: Int!) {
  products(first: $first, query: $query) {
    nodes {
      id
      title
      status
      tracksInventory
      totalInventory
      priceRangeV2 {
        minVariantPrice {
          amount
          currencyCode
        }
      }
    }
  }
}
"""

PRODUCT_STOCK_QUERY = """
query GetProductStock($id: ID!) {
  product(id: $id) {
    id
    title
    tracksInventory
    totalInventory
    variants(first: 50) {
      nodes {
        id
        title
        inventoryQuantity
      }
    }
  }
}
"""

GENERIC_ERROR_MESSAGE = "Layanan toko sedang bermasalah, coba lagi nanti"


def _determine_stock_status(tracks_inventory: bool, total_inventory: int | None) -> str:
    """Determine stock status based on inventory tracking and total quantity.

    Args:
        tracks_inventory: Whether the store tracks inventory for this product.
        total_inventory: The aggregated available stock count.

    Returns:
        One of 'in_stock', 'out_of_stock', or 'not_tracked'.
    """
    if not tracks_inventory:
        return "not_tracked"
    if total_inventory is not None and total_inventory > 0:
        return "in_stock"
    return "out_of_stock"


def search_products(query: str, limit: int = 5) -> dict[str, Any]:
    """Search products in Shopify by keyword.

    Sanitizes the input query to allow only alphanumeric characters, spaces,
    and hyphens, removes leading hyphens from words, truncates to 60 characters,
    and limits results to at most 10.

    Args:
        query: The user search keyword string.
        limit: The maximum number of results to return (default 5, max 10).

    Returns:
        A dictionary containing:
        - On success: {"ok": True, "results": list[dict]}
        - On failure: {"ok": False, "error": str}
    """
    # 1. Sanitize query: allow only letters, numbers, spaces, and hyphens
    sanitized = re.sub(r"[^a-zA-Z0-9 -]", "", query).strip()

    # 2. Remove leading hyphens from each word
    words = [word.lstrip("-") for word in sanitized.split()]
    cleaned_query = " ".join(word for word in words if word)

    # 3. Limit length to at most 60 characters
    cleaned_query = cleaned_query[:60].strip()

    if not cleaned_query:
        return {"ok": True, "results": []}

    # Enforce limit boundaries (minimum 1, maximum 10)
    clamped_limit = max(1, min(limit, 10))

    variables = {
        "query": cleaned_query,
        "first": clamped_limit,
    }

    try:
        data = graphql(SEARCH_PRODUCTS_QUERY, variables=variables)
    except Exception:
        # Avoid leaking technical error details, tokens, or URLs
        return {"ok": False, "error": GENERIC_ERROR_MESSAGE}

    nodes = data.get("products", {}).get("nodes", [])
    results: list[dict[str, Any]] = []

    for node in nodes:
        tracks_inventory = bool(node.get("tracksInventory", False))
        total_inventory = node.get("totalInventory")
        stock_status = _determine_stock_status(tracks_inventory, total_inventory)

        price_range = node.get("priceRangeV2") or {}
        min_variant_price = price_range.get("minVariantPrice") or {}
        min_price = min_variant_price.get("amount", "0.0")
        currency = min_variant_price.get("currencyCode", "")

        results.append({
            "id": node.get("id", ""),
            "title": node.get("title", ""),
            "status": node.get("status", ""),
            "min_price": min_price,
            "currency": currency,
            "stock_status": stock_status,
        })

    return {"ok": True, "results": results}


def get_stock(product_id: str) -> dict[str, Any]:
    """Retrieve title, variants with stock counts, and stock status for a product.

    Args:
        product_id: The Shopify product ID (e.g., 'gid://shopify/Product/123' or '123').

    Returns:
        A dictionary containing:
        - If not found: {"ok": True, "found": False}
        - If found: {"ok": True, "found": True, "title": str, "stock_status": str, "variants": list[dict]}
        - On failure: {"ok": False, "error": str}
    """
    clean_id = product_id.strip()
    if not clean_id:
        return {"ok": True, "found": False}

    # Support raw numeric IDs by converting to Shopify Global ID format
    if clean_id.isdigit():
        clean_id = f"gid://shopify/Product/{clean_id}"

    variables = {"id": clean_id}

    try:
        data = graphql(PRODUCT_STOCK_QUERY, variables=variables)
    except Exception:
        # Return generic error without technical details on API failure
        return {"ok": False, "error": GENERIC_ERROR_MESSAGE}

    product = data.get("product")
    if not product:
        return {"ok": True, "found": False}

    tracks_inventory = bool(product.get("tracksInventory", False))
    total_inventory = product.get("totalInventory")

    variant_nodes = product.get("variants", {}).get("nodes", [])

    # If product-level totalInventory is missing, calculate sum of variant quantities
    if total_inventory is None and variant_nodes:
        quantities = [
            v.get("inventoryQuantity")
            for v in variant_nodes
            if v.get("inventoryQuantity") is not None
        ]
        if quantities:
            total_inventory = sum(quantities)

    stock_status = _determine_stock_status(tracks_inventory, total_inventory)

    variants: list[dict[str, Any]] = []
    for node in variant_nodes:
        qty = node.get("inventoryQuantity")
        # For untracked products, variant stock is set to None instead of 0
        variant_stock = None if stock_status == "not_tracked" else (qty if qty is not None else 0)
        variants.append({
            "name": node.get("title", ""),
            "stock": variant_stock,
        })

    return {
        "ok": True,
        "found": True,
        "title": product.get("title", ""),
        "stock_status": stock_status,
        "variants": variants,
    }
