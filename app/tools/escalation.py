"""Customer service escalation ticketing tool for TokoBantu.

Manages SQLite storage for customer support tickets escalated to human staff.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

# Allowed values for validation
ALLOWED_REASONS = {
    "refund",
    "damaged_item",
    "complaint",
    "human_requested",
    "out_of_scope",
    "agent_stuck",
}

ALLOWED_URGENCIES = {
    "low",
    "medium",
    "high",
}

DEFAULT_DB_PATH = "data/tokobantu.db"
INVALID_DATA_ERROR = "Data tiket tidak valid"
DB_FAILURE_ERROR = "Gagal membuat tiket"
SUCCESS_MESSAGE = "Tiket sudah dibuat, tim kami akan menghubungi Anda"


def _get_db_path() -> Path:
    """Retrieve the SQLite database path from environment variable or default.

    Returns:
        Path object pointing to the configured database file.
    """
    raw_path = os.getenv("TOKOBANTU_DB", DEFAULT_DB_PATH)
    return Path(raw_path)


def _init_db(db_path: Path) -> None:
    """Initialize the tickets table in SQLite database if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                reason TEXT NOT NULL,
                urgency TEXT NOT NULL,
                order_number TEXT,
                status TEXT NOT NULL DEFAULT 'open'
            )
            """
        )
        conn.commit()


def create_escalation_ticket(
    summary: str,
    reason: str,
    urgency: str,
    order_number: str | None = None,
) -> dict[str, Any]:
    """Create a new human escalation ticket stored in SQLite.

    Validates input parameters, sanitizes summary and order number,
    and inserts a new ticket with status 'open'.

    Args:
        summary: Concise summary of the issue (truncated to max 500 chars).
        reason: Categorical reason for escalation (must be in ALLOWED_REASONS).
        urgency: Urgency level ('low', 'medium', or 'high').
        order_number: Optional order identifier (e.g. '#1001'). Stored as None
                      if missing or invalid format.

    Returns:
        A dictionary with operation status, ticket_id, and user message,
        or an error dictionary if validation or insertion fails.
    """
    # Validate reason
    if not isinstance(reason, str) or reason.strip() not in ALLOWED_REASONS:
        return {"ok": False, "error": INVALID_DATA_ERROR}

    # Validate urgency
    if not isinstance(urgency, str) or urgency.strip() not in ALLOWED_URGENCIES:
        return {"ok": False, "error": INVALID_DATA_ERROR}

    # Validate and sanitize summary (cannot be empty, max 500 characters)
    if not isinstance(summary, str):
        return {"ok": False, "error": INVALID_DATA_ERROR}

    clean_summary = summary.strip()
    if not clean_summary:
        return {"ok": False, "error": INVALID_DATA_ERROR}

    truncated_summary = clean_summary[:500]

    # Validate and normalize order_number: must be '#' followed by digits only
    clean_order_number: str | None = None
    if order_number is not None and isinstance(order_number, str):
        candidate_order = order_number.strip()
        if re.fullmatch(r"^#\d+$", candidate_order):
            clean_order_number = candidate_order

    created_at = datetime.now(timezone.utc).isoformat()
    db_path = _get_db_path()

    try:
        _init_db(db_path)
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tickets (created_at, summary, reason, urgency, order_number, status)
                VALUES (?, ?, ?, ?, ?, 'open')
                """,
                (
                    created_at,
                    truncated_summary,
                    reason.strip(),
                    urgency.strip(),
                    clean_order_number,
                ),
            )
            ticket_id = cursor.lastrowid
            conn.commit()

        return {
            "ok": True,
            "ticket_id": ticket_id,
            "message": SUCCESS_MESSAGE,
        }
    except Exception:
        # Return generic error message without exposing SQLite technical traces
        return {"ok": False, "error": DB_FAILURE_ERROR}


def list_open_tickets() -> list[dict[str, Any]]:
    """Retrieve all tickets currently marked with 'open' status.

    Returns:
        A list of dictionaries representing open escalation tickets.
    """
    db_path = _get_db_path()

    try:
        _init_db(db_path)
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, created_at, summary, reason, urgency, order_number, status
                FROM tickets
                WHERE status = ?
                ORDER BY id ASC
                """,
                ("open",),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []
