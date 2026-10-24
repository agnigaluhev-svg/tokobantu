"""Test script for escalation ticket tool using a temporary SQLite database.

Verifies:
1. Valid ticket creation
2. Invalid reason validation
3. Invalid urgency validation
4. Empty summary validation
5. Suspicious order number (e.g., SQL injection attempt '1; DROP TABLE')
6. list_open_tickets functionality

Does not print any secrets or tokens.
"""

import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Setup temporary database file path before importing escalation module
temp_dir = tempfile.mkdtemp(prefix="tokobantu_test_")
test_db_file = Path(temp_dir) / "test_escalation.db"
os.environ["TOKOBANTU_DB"] = str(test_db_file)

from app.tools.escalation import create_escalation_ticket, list_open_tickets


def print_case_result(case_num: int, title: str, passed: bool, detail: str) -> None:
    """Print formatted result for a test case."""
    status = "LULUS" if passed else "GAGAL"
    print(f"--- Kasus {case_num}: {title} ---")
    print(f"Hasil      : [{status}] {detail}")
    print()


def main() -> None:
    """Execute all escalation tool test cases against the temporary database."""
    print("=" * 60)
    print("UJI COBA ESCALATION TOOL DENGAN DATABASE SEMENTARA")
    print(f"Temp DB: {test_db_file}")
    print("=" * 60)
    print()

    total_passed = 0
    total_tests = 6

    try:
        # Kasus 1: Tiket valid
        res_1 = create_escalation_ticket(
            summary="Pelanggan meminta refund karena barang rusak saat pengiriman",
            reason="refund",
            urgency="high",
            order_number="#1001",
        )
        passed_1 = (
            res_1.get("ok") is True
            and isinstance(res_1.get("ticket_id"), int)
            and res_1.get("ticket_id", 0) > 0
            and res_1.get("message") == "Tiket sudah dibuat, tim kami akan menghubungi Anda"
        )
        detail_1 = f"ok={res_1.get('ok')}, ticket_id={res_1.get('ticket_id')}, msg={res_1.get('message')!r}"
        print_case_result(1, "Tiket valid (#1001, refund, high)", passed_1, detail_1)
        if passed_1:
            total_passed += 1

        # Kasus 2: Reason tidak valid
        res_2 = create_escalation_ticket(
            summary="Pelanggan ingin tanya produk",
            reason="invalid_reason_code",
            urgency="medium",
        )
        passed_2 = (
            res_2.get("ok") is False
            and res_2.get("error") == "Data tiket tidak valid"
        )
        detail_2 = f"ok={res_2.get('ok')}, error={res_2.get('error')!r}"
        print_case_result(2, "Reason tidak valid ('invalid_reason_code')", passed_2, detail_2)
        if passed_2:
            total_passed += 1

        # Kasus 3: Urgency tidak valid
        res_3 = create_escalation_ticket(
            summary="Komplain pengiriman lambat",
            reason="complaint",
            urgency="urgent_critical",
        )
        passed_3 = (
            res_3.get("ok") is False
            and res_3.get("error") == "Data tiket tidak valid"
        )
        detail_3 = f"ok={res_3.get('ok')}, error={res_3.get('error')!r}"
        print_case_result(3, "Urgency tidak valid ('urgent_critical')", passed_3, detail_3)
        if passed_3:
            total_passed += 1

        # Kasus 4: Summary kosong
        res_4 = create_escalation_ticket(
            summary="     ",
            reason="complaint",
            urgency="low",
        )
        passed_4 = (
            res_4.get("ok") is False
            and res_4.get("error") == "Data tiket tidak valid"
        )
        detail_4 = f"ok={res_4.get('ok')}, error={res_4.get('error')!r}"
        print_case_result(4, "Summary kosong (spasi saja)", passed_4, detail_4)
        if passed_4:
            total_passed += 1

        # Kasus 5: Order number aneh seperti "1; DROP TABLE"
        res_5 = create_escalation_ticket(
            summary="Uji coba karakter SQL injection pada nomor pesanan",
            reason="out_of_scope",
            urgency="medium",
            order_number="1; DROP TABLE tickets; --",
        )
        passed_5 = (
            res_5.get("ok") is True
            and isinstance(res_5.get("ticket_id"), int)
        )
        detail_5 = f"ok={res_5.get('ok')}, ticket_id={res_5.get('ticket_id')} (disimpan sebagai None)"
        print_case_result(5, "Order number mencurigakan ('1; DROP TABLE')", passed_5, detail_5)
        if passed_5:
            total_passed += 1

        # Kasus 6: list_open_tickets
        open_tickets = list_open_tickets()
        # Harus ada 2 tiket terbuka (Kasus 1 dan Kasus 5)
        passed_6 = (
            len(open_tickets) == 2
            and open_tickets[0].get("order_number") == "#1001"
            and open_tickets[1].get("order_number") is None
            and open_tickets[0].get("status") == "open"
        )
        detail_6 = (
            f"total_open={len(open_tickets)}, "
            f"ticket_1_order={open_tickets[0].get('order_number') if open_tickets else None!r}, "
            f"ticket_2_order={open_tickets[1].get('order_number') if len(open_tickets) > 1 else None!r}"
        )
        print_case_result(6, "list_open_tickets() untuk staf", passed_6, detail_6)
        if passed_6:
            total_passed += 1

    finally:
        # Clean up temporary database directory
        shutil.rmtree(temp_dir, ignore_errors=True)

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
