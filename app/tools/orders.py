"""Order retrieval and status verification tools for TokoBantu.

Provides functions to verify customer identity and retrieve order details
using the Shopify GraphQL Admin API. Read-only operation.
"""

import re
from typing import Any
from app.shopify_client import graphql

# GraphQL query to retrieve an order by its name/number
GET_ORDER_BY_NUMBER_QUERY = """
query GetOrderByNumber($query: String!) {
  orders(first: 1, query: $query) {
    nodes {
      id
      name
      createdAt
      displayFinancialStatus
      displayFulfillmentStatus
      cancelledAt
      email
      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      lineItems(first: 50) {
        nodes {
          title
          quantity
        }
      }
      fulfillments {
        trackingInfo {
          company
          number
          url
        }
      }
    }
  }
}
"""

UNVERIFIED_MESSAGE = "Pesanan tidak ditemukan atau email tidak cocok"
GENERIC_ERROR_MESSAGE = "Layanan toko sedang bermasalah, coba lagi nanti"


def normalize_order_number(order_number: str) -> str | None:
    """Normalize and validate an order number string.

    Accepts formats such as '1001', '#1001', or '# 1001' and standardizes
    them to '#1001'. If the normalized result does not consist of '#'
    followed strictly by digits, returns None.

    Args:
        order_number: The input order identifier.

    Returns:
        The standardized order number (e.g., '#1001'), or None if invalid.
    """
    if not isinstance(order_number, str):
        return None

    raw = order_number.strip()
    if raw.startswith("#"):
        digits_part = raw[1:].strip()
        normalized = f"#{digits_part}"
    else:
        normalized = f"#{raw}"

    if not re.fullmatch(r"^#\d+$", normalized):
        return None

    return normalized


def get_order_status(order_number: str, email: str) -> dict[str, Any]:
    """Retrieve order status and details after verifying customer email.

    Normalizes the order number and queries Shopify Admin API. If the order
    is not found or the provided email does not match the order, returns an
    identical unverified response to prevent order enumeration attacks.

    Personal identifiable information (customer full name, address, phone)
    is intentionally excluded from the response.

    Args:
        order_number: Customer-provided order number (e.g., '1001' or '#1001').
        email: Customer-provided email address for verification.

    Returns:
        A dictionary with verification status and sanitized order details,
        or an error structure if the service is unreachable.
    """
    unverified_response: dict[str, Any] = {
        "ok": True,
        "verified": False,
        "message": UNVERIFIED_MESSAGE,
    }

    normalized_order = normalize_order_number(order_number)
    if normalized_order is None:
        return unverified_response

    clean_email = email.strip().lower() if isinstance(email, str) else ""
    if not clean_email:
        return unverified_response

    variables = {
        "query": f"name:{normalized_order}",
    }

    try:
        data = graphql(GET_ORDER_BY_NUMBER_QUERY, variables=variables)
    except Exception:
        # Return generic error message without leaking technical or sensitive details
        return {
            "ok": False,
            "error": GENERIC_ERROR_MESSAGE,
        }

    nodes = data.get("orders", {}).get("nodes", [])
    if not nodes:
        return unverified_response

    order = nodes[0]

    # Verify that the retrieved order name matches the requested order number
    order_name = (order.get("name") or "").strip()
    normalized_order_name = f"#{order_name.lstrip('#')}" if order_name else ""
    if order_name != normalized_order and normalized_order_name != normalized_order:
        return unverified_response

    # Verify email against order contact email
    order_email = (order.get("email") or "").strip().lower()
    if clean_email != order_email:
        return unverified_response

    # Extract purchased items (title and quantity only)
    line_items_nodes = (order.get("lineItems") or {}).get("nodes", [])
    items: list[dict[str, Any]] = [
        {
            "title": item.get("title", ""),
            "quantity": item.get("quantity", 0),
        }
        for item in line_items_nodes
    ]

    # Extract fulfillment tracking information (company, number, and url)
    fulfillments = order.get("fulfillments") or []
    tracking: list[dict[str, Any]] = []
    for fulfillment in fulfillments:
        tracking_info_list = fulfillment.get("trackingInfo") or []
        for info in tracking_info_list:
            tracking.append({
                "company": info.get("company"),
                "number": info.get("number"),
                "url": info.get("url"),
            })

    # Extract monetary totals
    total_price_set = order.get("totalPriceSet") or {}
    shop_money = total_price_set.get("shopMoney") or {}
    total = shop_money.get("amount", "0.0")
    currency = shop_money.get("currencyCode", "")

    return {
        "ok": True,
        "verified": True,
        "order_number": order.get("name") or normalized_order,
        "created_at": order.get("createdAt", ""),
        "payment_status": order.get("displayFinancialStatus") or "",
        "fulfillment_status": order.get("displayFulfillmentStatus") or "",
        "cancelled": bool(order.get("cancelledAt")),
        "items": items,
        "tracking": tracking,
        "total": total,
        "currency": currency,
    }
