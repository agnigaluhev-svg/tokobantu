"""Shopify Admin API client for TokoBantu.

Handles OAuth client credentials authentication and GraphQL queries.
All operations are read-only.
"""

import os
import time
from typing import Any
from dotenv import load_dotenv
import httpx

# Load environment variables from .env file without reading it directly
load_dotenv()

# In-memory token cache
_cached_token: str | None = None
_token_expires_at: float = 0.0


def _get_env_var(key: str) -> str:
    """Retrieve an environment variable or raise an error if missing.

    Args:
        key: The name of the environment variable.

    Returns:
        The string value of the environment variable.

    Raises:
        ValueError: If the environment variable is not set or empty.
    """
    value = os.getenv(key)
    if not value or not value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return value.strip()


def _get_store_domain() -> str:
    """Format and validate the Shopify store domain from environment.

    Returns:
        A clean domain string (e.g., 'your-store.myshopify.com').
    """
    store = _get_env_var("SHOPIFY_STORE")
    domain = store.replace("https://", "").replace("http://", "").rstrip("/")
    if "." not in domain:
        domain = f"{domain}.myshopify.com"
    return domain


def get_access_token() -> str:
    """Get a valid Shopify Admin API access token.

    Uses the client credentials grant type. Caches the token in memory
    and refreshes it if less than 5 minutes remain before expiry.

    Returns:
        A valid access token string.

    Raises:
        RuntimeError: If token retrieval fails.
    """
    global _cached_token, _token_expires_at

    now = time.time()
    # 5 minutes buffer (300 seconds)
    if _cached_token is not None and now < (_token_expires_at - 300):
        return _cached_token

    store_domain = _get_store_domain()
    client_id = _get_env_var("SHOPIFY_CLIENT_ID")
    client_secret = _get_env_var("SHOPIFY_CLIENT_SECRET")

    token_url = f"https://{store_domain}/admin/oauth/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    try:
        response = httpx.post(
            token_url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15.0,
        )
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Network error while connecting to Shopify OAuth endpoint: {exc.__class__.__name__}"
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to obtain Shopify access token (HTTP {response.status_code}): {response.text}"
        )

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError("Shopify OAuth response could not be parsed as JSON.") from exc

    token = data.get("access_token")
    if not token:
        raise RuntimeError("Shopify OAuth response did not contain an access_token.")

    # Default to 86400 seconds (24 hours) if expires_in is not provided
    expires_in = data.get("expires_in", 86400)
    _cached_token = token
    _token_expires_at = now + float(expires_in)

    return _cached_token


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against Shopify Admin API version 2026-10.

    Args:
        query: GraphQL query string.
        variables: Optional variables mapping for the GraphQL query.

    Returns:
        The 'data' dictionary from Shopify's response payload.

    Raises:
        RuntimeError: If the HTTP request fails or GraphQL errors are returned.
    """
    token = get_access_token()
    store_domain = _get_store_domain()
    url = f"https://{store_domain}/admin/api/2026-10/graphql.json"

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token,
    }
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=20.0)
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Network error while executing Shopify GraphQL request: {exc.__class__.__name__}"
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Shopify GraphQL request failed with HTTP status {response.status_code}: {response.text}"
        )

    try:
        result = response.json()
    except Exception as exc:
        raise RuntimeError("Failed to decode JSON response from Shopify GraphQL API.") from exc

    if "errors" in result:
        raise RuntimeError(f"Shopify GraphQL returned errors: {result['errors']}")

    data = result.get("data")
    if data is None:
        return {}

    return data
