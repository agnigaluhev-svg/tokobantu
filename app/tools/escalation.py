"""Escalation ticket tool for TokoBantu (SQLite bawaan Python, tanpa library tambahan)."""

import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = "data/tokobantu.db"

VALID_REASONS = {
    "refund", "damaged_item", "complaint",
    "human_requested", "out_of_scope", "agent_stuck",
}
VALID_URGENCIES = {"low", "medium", "high"}

ORDER_NUMBER_PATTERN = re.compile(r"^#\d+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?\d{8,15}$")

MESSAGE_WITH_CONTACT = "Tiket sudah dibuat, tim kami akan menghubungi Anda"


def _get_db_path() -> str:
    """Return the SQLite file path from TOKOBANTU_DB or the default."""
    return os.getenv("TOKOBANTU_DB", DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    """Open the database, create the folder/table, and migrate older tables."""
    path = _get_db_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            summary TEXT NOT NULL,
            reason TEXT NOT NULL,
            urgency TEXT NOT NULL,
            order_number TEXT,
            contact TEXT,
            status TEXT NOT NULL DEFAULT 'open'
        )
        """
    )
    columns = [row[1] for row in conn.execute("PRAGMA table_info(tickets)")]
    if "contact" not in columns:
        # Migrasi aman untuk tabel lama: menambah kolom, tidak menghapus data.
        conn.execute("ALTER TABLE tickets ADD COLUMN contact TEXT")
    conn.commit()
    return conn


def _clean_order_number(order_number: Any) -> str | None:
    """Return a valid '#1234' order number, otherwise None."""
    if not isinstance(order_number, str):
        return None
    value = order_number.strip()
    return value if ORDER_NUMBER_PATTERN.match(value) else None


def _clean_contact(contact: Any) -> str | None:
    """Return a valid email or phone number (max 100 chars), otherwise None."""
    if not isinstance(contact, str):
        return None
    value = contact.strip()[:100]
    if not value:
        return None
    if EMAIL_PATTERN.match(value):
        return value.lower()
    digits = re.sub(r"[\s\-().]", "", value)
    return digits if PHONE_PATTERN.match(digits) else None


def create_escalation_ticket(
    summary: str,
    reason: str,
    urgency: str,
    order_number: str | None = None,
    contact: str | None = None,
) -> dict[str, Any]:
    """Create an escalation ticket for human staff.

    A ticket is created only when the customer supplied a valid order number
    and a contact address. Returns a ticket id on success, or a safe error.
    """
    clean_summary = summary.strip()[:500] if isinstance(summary, str) else ""
    if (
        not clean_summary
        or not isinstance(reason, str) or reason not in VALID_REASONS
        or not isinstance(urgency, str) or urgency not in VALID_URGENCIES
    ):
        return {"ok": False, "error": "Data tiket tidak valid"}

    clean_order = _clean_order_number(order_number)
    if clean_order is None:
        return {"ok": False, "error": "Nomor pesanan diperlukan untuk membuat tiket"}

    clean_contact = _clean_contact(contact)
    if clean_contact is None:
        return {"ok": False, "error": "Email atau nomor telepon diperlukan untuk membuat tiket"}

    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with closing(_connect()) as conn:
            cursor = conn.execute(
                "INSERT INTO tickets "
                "(created_at, summary, reason, urgency, order_number, contact, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'open')",
                (created_at, clean_summary, reason, urgency, clean_order, clean_contact),
            )
            conn.commit()
            ticket_id = cursor.lastrowid
    except (sqlite3.Error, OSError):
        return {"ok": False, "error": "Gagal membuat tiket"}

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "has_contact": True,
        "message": MESSAGE_WITH_CONTACT,
    }


def list_open_tickets() -> list[dict[str, Any]]:
    """Return all open tickets (oldest first) for staff."""
    try:
        with closing(_connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, created_at, summary, reason, urgency, order_number, "
                "contact, status FROM tickets WHERE status = ? ORDER BY id ASC",
                ("open",),
            ).fetchall()
            return [dict(row) for row in rows]
    except (sqlite3.Error, OSError):
        return []
