"""Test script for store policy retrieval tool.

Tests:
1. 'returns' (standard English key)
2. 'Retur ' (case-insensitive and trailing whitespace normalization)
3. 'pengiriman' (Indonesian alias mapping to 'shipping')
4. Unknown topic (e.g. 'diskon')
5. Empty input ('')
6. Path traversal attempt ('../.env')

Does not print any tokens or secrets.
"""

from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.tools.policy import get_store_policy


def print_case_result(case_num: int, input_topic: str, passed: bool, detail: str) -> None:
    """Print formatted result for a test case."""
    status = "LULUS" if passed else "GAGAL"
    print(f"--- Kasus {case_num}: Input {input_topic!r} ---")
    print(f"Hasil      : [{status}] {detail}")
    print()


def main() -> None:
    """Execute all test cases for get_store_policy."""
    print("=" * 60)
    print("UJI COBA GET_STORE_POLICY")
    print("=" * 60)
    print()

    total_passed = 0
    total_tests = 6
    expected_topics = ["returns", "shipping", "payment", "contact"]

    # Kasus 1: "returns"
    res_1 = get_store_policy("returns")
    passed_1 = (
        res_1.get("ok") is True
        and res_1.get("found") is True
        and res_1.get("topic") == "returns"
        and isinstance(res_1.get("policy"), str)
        and len(res_1.get("policy", "")) > 0
    )
    detail_1 = f"found={res_1.get('found')}, topic={res_1.get('topic')!r}, policy_len={len(res_1.get('policy', ''))}"
    print_case_result(1, "returns", passed_1, detail_1)
    if passed_1:
        total_passed += 1

    # Kasus 2: "Retur "
    res_2 = get_store_policy("Retur ")
    passed_2 = (
        res_2.get("ok") is True
        and res_2.get("found") is True
        and res_2.get("topic") == "returns"
        and isinstance(res_2.get("policy"), str)
        and len(res_2.get("policy", "")) > 0
    )
    detail_2 = f"found={res_2.get('found')}, topic={res_2.get('topic')!r}, policy_len={len(res_2.get('policy', ''))}"
    print_case_result(2, "Retur ", passed_2, detail_2)
    if passed_2:
        total_passed += 1

    # Kasus 3: "pengiriman"
    res_3 = get_store_policy("pengiriman")
    passed_3 = (
        res_3.get("ok") is True
        and res_3.get("found") is True
        and res_3.get("topic") == "shipping"
        and isinstance(res_3.get("policy"), str)
        and len(res_3.get("policy", "")) > 0
    )
    detail_3 = f"found={res_3.get('found')}, topic={res_3.get('topic')!r}, policy_len={len(res_3.get('policy', ''))}"
    print_case_result(3, "pengiriman", passed_3, detail_3)
    if passed_3:
        total_passed += 1

    # Kasus 4: Topik tidak dikenal ("diskon")
    res_4 = get_store_policy("diskon")
    passed_4 = (
        res_4.get("ok") is True
        and res_4.get("found") is False
        and res_4.get("available_topics") == expected_topics
        and "_note" not in res_4.get("available_topics", [])
    )
    detail_4 = f"found={res_4.get('found')}, available_topics={res_4.get('available_topics')}"
    print_case_result(4, "diskon", passed_4, detail_4)
    if passed_4:
        total_passed += 1

    # Kasus 5: Input kosong ("")
    res_5 = get_store_policy("   ")
    passed_5 = (
        res_5.get("ok") is True
        and res_5.get("found") is False
        and res_5.get("available_topics") == expected_topics
    )
    detail_5 = f"found={res_5.get('found')}, available_topics={res_5.get('available_topics')}"
    print_case_result(5, "   ", passed_5, detail_5)
    if passed_5:
        total_passed += 1

    # Kasus 6: Path traversal attempt ("../.env")
    res_6 = get_store_policy("../.env")
    passed_6 = (
        res_6.get("ok") is True
        and res_6.get("found") is False
        and res_6.get("available_topics") == expected_topics
    )
    detail_6 = f"found={res_6.get('found')} (tidak memuat .env), available_topics={res_6.get('available_topics')}"
    print_case_result(6, "../.env", passed_6, detail_6)
    if passed_6:
        total_passed += 1

    total_failed = total_tests - total_passed
    print("=" * 60)
    print("RINGKASAN UJI COBA")
    print("=" * 60)
    print(f"Total kasus : {total_tests}")
    print(f"Lulus       : {total_passed}")
    print(f"Gagal       : {total_failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
