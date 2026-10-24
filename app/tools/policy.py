"""Store policy retrieval tool for TokoBantu.

Loads and exposes store policies (returns, shipping, payment, contact)
from app/policies/store_policies.json with alias resolution.
"""

import json
from pathlib import Path
from typing import Any

# Path to the store policies JSON file relative to this module's directory
POLICIES_FILE_PATH = Path(__file__).resolve().parent.parent / "policies" / "store_policies.json"

# Mapping of Indonesian aliases to standard policy keys
TOPIC_ALIASES: dict[str, str] = {
    "retur": "returns",
    "pengiriman": "shipping",
    "pembayaran": "payment",
    "kontak": "contact",
}

GENERIC_ERROR_MESSAGE = "Kebijakan toko tidak dapat dimuat"


def _load_policies_data() -> dict[str, Any] | None:
    """Load store policies JSON file safely.

    Returns:
        Dictionary of policy keys and contents, or None if reading fails.
    """
    try:
        with open(POLICIES_FILE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return None
    except Exception:
        return None


def get_store_policy(topic: str) -> dict[str, Any]:
    """Retrieve store policy text by topic or Indonesian alias.

    Normalizes topic string, maps synonyms, and returns policy text.
    Private metadata keys starting with '_' are excluded from available topics
    and cannot be queried.

    Args:
        topic: The policy topic name or alias (e.g. 'returns', 'retur', 'pengiriman').

    Returns:
        A dictionary containing:
        - If found: {"ok": True, "found": True, "topic": str, "policy": str}
        - If not found: {"ok": True, "found": False, "available_topics": list[str]}
        - On file read failure: {"ok": False, "error": str}
    """
    policies = _load_policies_data()
    if policies is None:
        return {"ok": False, "error": GENERIC_ERROR_MESSAGE}

    # Extract all public topics (exclude internal metadata keys prefixed with '_')
    available_topics = [key for key in policies.keys() if not key.startswith("_")]

    # Normalize input: lowercase and strip surrounding whitespace
    clean_topic = topic.strip().lower() if isinstance(topic, str) else ""

    # Map Indonesian alias if applicable
    resolved_topic = TOPIC_ALIASES.get(clean_topic, clean_topic)

    # Check if resolved topic exists in public policies
    if resolved_topic in available_topics and isinstance(policies.get(resolved_topic), str):
        return {
            "ok": True,
            "found": True,
            "topic": resolved_topic,
            "policy": policies[resolved_topic],
        }

    return {
        "ok": True,
        "found": False,
        "available_topics": available_topics,
    }
