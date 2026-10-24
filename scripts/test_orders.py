"""Test script to verify order retrieval and status verification tool.

Executes test cases against Shopify development store orders:
- #1001 + budi.santoso@example.com (verified, Paid, Fulfilled, 1 item)
- #1001 + siti.rahma@example.com (unverified)
- #1002 + budi.santoso@example.com (verified, Paid, Unfulfilled)
- #1003 + siti.rahma@example.com (verified, Paid, Fulfilled)
- #1004 + siti.rahma@example.com (verified, payment pending, Unfulfilled, 2 items)
- #1005 + andi.wijaya@example.com (verified, cancelled True)
- #1006 + dewi.lestari@example.com (verified, partially fulfilled)
- #9999 + budi.santoso@example.com (unverified)
- "1001" + "  BUDI.SANTOSO@EXAMPLE.COM " (verified)
- "1001 OR 1" + budi.santoso@example.com (unverified)

Does not print any API tokens or sensitive credentials.
"""

import sys
from pathlib import Path
from typing import Any, Callable

# Ensure project root is in sys.path when script is executed directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.tools.orders import get_order_status


def evaluate_test_case(
    case_num: int,
    order_number: str,
    email: str,
    description: str,
    validator: Callable[[dict[str, Any]], tuple[bool, str]],
) -> bool:
    """Execute a single test case, run validator, and print formatted summary.

    Args:
        case_num: Numeric order of the test case.
        order_number: Order number input passed to get_order_status.
        email: Email address input passed to get_order_status.
        description: Expected outcome description.
        validator: Function returning (passed: bool, message: str).

    Returns:
        True if the test passed, False otherwise.
    """
    print(f"--- Kasus {case_num}: {order_number!r} + {email!r} ---")
    print(f"Ekspektasi : {description}")

    result = get_order_status(order_number, email)

    passed, detail = validator(result)
    status_label = "LULUS" if passed else "GAGAL"
    print(f"Hasil      : [{status_label}] {detail}")
    print()
    return passed


def main() -> None:
    """Run all 10 order verification test cases and display a summary."""
    print("=" * 60)
    print("UJI COBA GET_ORDER_STATUS DENGAN SHOPIFY ADMIN API")
    print("=" * 60)
    print()

    tests: list[tuple[str, str, str, Callable[[dict[str, Any]], tuple[bool, str]]]] = []

    # Kasus 1: #1001 + budi.santoso@example.com -> terverifikasi, Paid, Fulfilled, 1 item
    def check_case_1(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        paid = res.get("payment_status", "").upper() == "PAID"
        fulfilled = res.get("fulfillment_status", "").upper() == "FULFILLED"
        item_count = len(res.get("items", []))
        passed = ok and verified and paid and fulfilled and (item_count == 1)
        detail = (
            f"verified={verified}, payment={res.get('payment_status')}, "
            f"fulfillment={res.get('fulfillment_status')}, items={item_count}"
        )
        return passed, detail

    tests.append((
        "#1001",
        "budi.santoso@example.com",
        "Terverifikasi, Paid, Fulfilled, 1 item",
        check_case_1,
    ))

    # Kasus 2: #1001 + siti.rahma@example.com -> tidak terverifikasi
    def check_case_2(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is False
        msg = res.get("message") == "Pesanan tidak ditemukan atau email tidak cocok"
        passed = ok and verified and msg
        detail = f"verified={res.get('verified')}, message={res.get('message')!r}"
        return passed, detail

    tests.append((
        "#1001",
        "siti.rahma@example.com",
        "Tidak terverifikasi",
        check_case_2,
    ))

    # Kasus 3: #1002 + budi.santoso@example.com -> Paid, Unfulfilled
    def check_case_3(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        paid = res.get("payment_status", "").upper() == "PAID"
        unfulfilled = res.get("fulfillment_status", "").upper() == "UNFULFILLED"
        passed = ok and verified and paid and unfulfilled
        detail = (
            f"verified={verified}, payment={res.get('payment_status')}, "
            f"fulfillment={res.get('fulfillment_status')}"
        )
        return passed, detail

    tests.append((
        "#1002",
        "budi.santoso@example.com",
        "Terverifikasi, Paid, Unfulfilled",
        check_case_3,
    ))

    # Kasus 4: #1003 + siti.rahma@example.com -> Paid, Fulfilled
    def check_case_4(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        paid = res.get("payment_status", "").upper() == "PAID"
        fulfilled = res.get("fulfillment_status", "").upper() == "FULFILLED"
        passed = ok and verified and paid and fulfilled
        detail = (
            f"verified={verified}, payment={res.get('payment_status')}, "
            f"fulfillment={res.get('fulfillment_status')}"
        )
        return passed, detail

    tests.append((
        "#1003",
        "siti.rahma@example.com",
        "Terverifikasi, Paid, Fulfilled",
        check_case_4,
    ))

    # Kasus 5: #1004 + siti.rahma@example.com -> payment pending, Unfulfilled, total quantity 2
    def check_case_5(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        pending = res.get("payment_status", "").upper() == "PENDING"
        unfulfilled = res.get("fulfillment_status", "").upper() == "UNFULFILLED"
        items = res.get("items", [])
        total_quantity = sum(item.get("quantity", 0) for item in items)
        passed = ok and verified and pending and unfulfilled and (total_quantity == 2)
        detail = (
            f"verified={verified}, payment={res.get('payment_status')}, "
            f"fulfillment={res.get('fulfillment_status')}, lines={len(items)}, "
            f"total_quantity={total_quantity}"
        )
        return passed, detail

    tests.append((
        "#1004",
        "siti.rahma@example.com",
        "Terverifikasi, payment pending, Unfulfilled, total quantity 2",
        check_case_5,
    ))

    # Kasus 6: #1005 + andi.wijaya@example.com -> cancelled True
    def check_case_6(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        cancelled = res.get("cancelled") is True
        passed = ok and verified and cancelled
        detail = f"verified={verified}, cancelled={res.get('cancelled')}"
        return passed, detail

    tests.append((
        "#1005",
        "andi.wijaya@example.com",
        "Terverifikasi, cancelled True",
        check_case_6,
    ))

    # Kasus 7: #1006 + dewi.lestari@example.com -> partially fulfilled
    def check_case_7(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        partially = res.get("fulfillment_status", "").upper() == "PARTIALLY_FULFILLED"
        passed = ok and verified and partially
        detail = f"verified={verified}, fulfillment={res.get('fulfillment_status')}"
        return passed, detail

    tests.append((
        "#1006",
        "dewi.lestari@example.com",
        "Terverifikasi, partially fulfilled",
        check_case_7,
    ))

    # Kasus 8: #9999 + budi.santoso@example.com -> tidak terverifikasi
    def check_case_8(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is False
        msg = res.get("message") == "Pesanan tidak ditemukan atau email tidak cocok"
        passed = ok and verified and msg
        detail = f"verified={res.get('verified')}, message={res.get('message')!r}"
        return passed, detail

    tests.append((
        "#9999",
        "budi.santoso@example.com",
        "Tidak terverifikasi (pesanan tidak ada)",
        check_case_8,
    ))

    # Kasus 9: "1001" + "  BUDI.SANTOSO@EXAMPLE.COM " -> terverifikasi
    def check_case_9(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is True
        order_num = res.get("order_number") == "#1001"
        passed = ok and verified and order_num
        detail = f"verified={verified}, order_number={res.get('order_number')!r}"
        return passed, detail

    tests.append((
        "1001",
        "  BUDI.SANTOSO@EXAMPLE.COM ",
        "Terverifikasi (normalisasi nomor dan email)",
        check_case_9,
    ))

    # Kasus 10: "1001 OR 1" + budi.santoso@example.com -> tidak terverifikasi
    def check_case_10(res: dict[str, Any]) -> tuple[bool, str]:
        ok = res.get("ok") is True
        verified = res.get("verified") is False
        msg = res.get("message") == "Pesanan tidak ditemukan atau email tidak cocok"
        passed = ok and verified and msg
        detail = f"verified={res.get('verified')}, message={res.get('message')!r}"
        return passed, detail

    tests.append((
        "1001 OR 1",
        "budi.santoso@example.com",
        "Tidak terverifikasi (input injection / format tidak valid)",
        check_case_10,
    ))

    total_passed = 0
    total_tests = len(tests)

    for idx, (order_num, email, desc, validator) in enumerate(tests, start=1):
        if evaluate_test_case(idx, order_num, email, desc, validator):
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
