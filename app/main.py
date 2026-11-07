"""FastAPI web API for TokoBantu."""

from collections import deque
from dataclasses import dataclass, field
import hashlib
import hmac
import json
from pathlib import Path
import os
import secrets
import threading
import time
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Path as ApiPath, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import run_agent
from app.tools.escalation import close_ticket, list_open_tickets

SESSION_LIMIT = 500
SESSION_TTL_SECONDS = 30 * 60
HISTORY_LIMIT = 20
RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 60
RATE_LIMIT_REPLY = "Pesan Anda terlalu cepat. Silakan coba lagi sebentar."


@dataclass
class SessionState:
    """Store one chat history and activity timestamp in memory."""

    history: list[Any] = field(default_factory=list)
    last_active: float = field(default_factory=time.monotonic)
    lock: Any = field(default_factory=threading.Lock)


_state_lock = threading.RLock()
_sessions: dict[str, SessionState] = {}
_request_times: dict[tuple[str, str], deque[float]] = {}

app = FastAPI(title="TokoBantu")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8001", "http://localhost:8001"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


class ChatRequest(BaseModel):
    """Validate a customer message and its UUID session identifier."""

    session_id: UUID
    message: str = Field(max_length=1000)


def _prune_expired_sessions(now: float) -> None:
    """Remove sessions inactive for more than the configured lifetime."""
    expired = [
        session_id
        for session_id, state in _sessions.items()
        if now - state.last_active >= SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def _allow_request(session_id: str, client_ip: str, now: float) -> bool:
    """Apply sliding-window rate limits for both session and client IP."""
    keys = (("session", session_id), ("ip", client_ip))
    cutoff = now - RATE_WINDOW_SECONDS
    for key, timestamps in list(_request_times.items()):
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if not timestamps:
            _request_times.pop(key, None)

    if any(len(_request_times.get(key, ())) >= RATE_LIMIT for key in keys):
        return False
    for key in keys:
        _request_times.setdefault(key, deque()).append(now)
    return True


def _database_url() -> str:
    """Return the configured hosted database URL, if present."""
    return os.getenv("TOKOBANTU_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()


def _uses_shared_storage() -> bool:
    """Use shared database state in Vercel, with SQLite/in-memory state locally."""
    return bool(_database_url()) or _requires_shared_storage()


def _requires_shared_storage() -> bool:
    """Check whether this deployment must fail rather than use local storage."""
    return bool(os.getenv("VERCEL")) or os.getenv("TOKOBANTU_STORAGE_MODE") == "postgres"


def _require_shared_storage() -> None:
    """Fail staff operations clearly if Vercel has no persistent database URL."""
    if _requires_shared_storage() and not _database_url():
        raise HTTPException(status_code=503, detail="Database persisten belum dikonfigurasi")


def _verify_shared_storage() -> None:
    """Verify the configured hosted database before staff ticket operations."""
    _require_shared_storage()
    if not _database_url():
        return
    try:
        with _connect_cloud_database() as conn:
            _ensure_cloud_tables(conn)
            conn.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Database tiket sedang tidak tersedia") from None


def _connect_cloud_database() -> Any:
    """Open a short-lived Postgres connection for serverless storage."""
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_database_url(), row_factory=dict_row, connect_timeout=10)


def _ensure_cloud_tables(conn: Any) -> None:
    """Create the short-lived chat session and rate-limit tables if needed."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id UUID PRIMARY KEY,
            history JSONB NOT NULL,
            last_active TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_rate_events (
            event_id BIGSERIAL PRIMARY KEY,
            key_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS chat_rate_events_key_time_idx "
        "ON chat_rate_events (key_hash, created_at)"
    )


def _rate_key_hash(scope: str, value: str) -> str:
    """Hash a rate-limit key so raw session ids and client IPs are not stored."""
    secret = (
        os.getenv("RATE_LIMIT_SECRET", "")
        or os.getenv("STAFF_TOKEN", "")
        or os.getenv("GEMINI_API_KEY", "")
    )
    if not secret:
        raise RuntimeError("Rate limit secret is not configured")
    message = f"{scope}:{value}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _allow_cloud_request(session_id: str, client_ip: str) -> bool:
    """Apply shared, rolling rate limits using hashed identifiers in Postgres."""
    key_hashes = [
        _rate_key_hash("session", session_id),
        _rate_key_hash("ip", client_ip),
    ]
    try:
        with _connect_cloud_database() as conn:
            _ensure_cloud_tables(conn)
            for key_hash in sorted(key_hashes):
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key_hash,))
            conn.execute(
                "DELETE FROM chat_rate_events "
                "WHERE created_at <= NOW() - (%s * INTERVAL '1 second')",
                (RATE_WINDOW_SECONDS,),
            )
            rows = conn.execute(
                "SELECT key_hash, COUNT(*) AS event_count FROM chat_rate_events "
                "WHERE key_hash = ANY(%s) "
                "AND created_at > NOW() - (%s * INTERVAL '1 second') "
                "GROUP BY key_hash",
                (key_hashes, RATE_WINDOW_SECONDS),
            ).fetchall()
            if any(row["event_count"] >= RATE_LIMIT for row in rows):
                conn.commit()
                return False
            conn.executemany(
                "INSERT INTO chat_rate_events (key_hash) VALUES (%s)",
                [(key_hash,) for key_hash in key_hashes],
            )
            conn.commit()
        return True
    except Exception as exc:
        raise RuntimeError("Shared rate limit storage is unavailable") from exc


def _get_cloud_history(session_id: str) -> list[Any]:
    """Load recent conversation history and remove expired sessions."""
    with _connect_cloud_database() as conn:
        _ensure_cloud_tables(conn)
        conn.execute(
            "DELETE FROM chat_sessions "
            "WHERE last_active <= NOW() - (%s * INTERVAL '1 second')",
            (SESSION_TTL_SECONDS,),
        )
        row = conn.execute(
            "SELECT history FROM chat_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
        conn.commit()
    if not row:
        return []
    history = row["history"]
    return history if isinstance(history, list) else json.loads(history)


def _save_cloud_history(session_id: str, history: list[Any]) -> None:
    """Persist bounded chat history and refresh its expiration timestamp."""
    with _connect_cloud_database() as conn:
        _ensure_cloud_tables(conn)
        # Serialize capacity enforcement so concurrent serverless instances do
        # not leave more than SESSION_LIMIT active sessions behind.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("tokobantu_chat_sessions_capacity",),
        )
        conn.execute(
            "DELETE FROM chat_sessions "
            "WHERE last_active <= NOW() - (%s * INTERVAL '1 second')",
            (SESSION_TTL_SECONDS,),
        )
        conn.execute(
            "INSERT INTO chat_sessions (session_id, history, last_active) "
            "VALUES (%s, %s::jsonb, NOW()) "
            "ON CONFLICT (session_id) DO UPDATE "
            "SET history = EXCLUDED.history, last_active = NOW()",
            (session_id, json.dumps(history[-HISTORY_LIMIT:])),
        )
        conn.execute(
            "DELETE FROM chat_sessions WHERE session_id IN ("
            "SELECT session_id FROM chat_sessions "
            "ORDER BY last_active DESC, session_id ASC OFFSET %s"
            ")",
            (SESSION_LIMIT,),
        )
        conn.commit()


def _get_session(session_id: str, now: float) -> SessionState:
    """Return an active session, evicting stale or least-recently-used data."""
    _prune_expired_sessions(now)
    state = _sessions.get(session_id)
    if state is None:
        if len(_sessions) >= SESSION_LIMIT:
            oldest_id = min(_sessions, key=lambda key: _sessions[key].last_active)
            _sessions.pop(oldest_id, None)
        state = SessionState()
        _sessions[session_id] = state
    state.last_active = now
    return state


def _authorize_staff(request: Request) -> None:
    """Require a configured staff token using a constant-time comparison."""
    expected = os.getenv("STAFF_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Akses staf belum dikonfigurasi")

    authorization = request.headers.get("Authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not supplied:
        raise HTTPException(status_code=401, detail="Autentikasi diperlukan")
    if not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Autentikasi tidak valid")


@app.get("/health")
def health() -> dict[str, str]:
    """Return service readiness without exposing database configuration."""
    if _requires_shared_storage():
        _require_shared_storage()
        try:
            with _connect_cloud_database() as conn:
                conn.execute("SELECT 1")
                conn.commit()
        except Exception:
            raise HTTPException(status_code=503, detail="Database persisten tidak tersedia") from None
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest, request: Request) -> dict[str, Any]:
    """Run one agent turn and retain a bounded in-memory conversation."""
    session_id = str(body.session_id)
    client_ip = request.client.host if request.client else "unknown"
    if os.getenv("VERCEL"):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for.strip():
            client_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
    now = time.monotonic()

    if _uses_shared_storage():
        try:
            allowed = _allow_cloud_request(session_id, client_ip)
            history = _get_cloud_history(session_id) if allowed else []
        except Exception:
            raise HTTPException(status_code=503, detail="Layanan chat sedang disiapkan") from None
        if not allowed:
            raise HTTPException(status_code=429, detail=RATE_LIMIT_REPLY)
        result = run_agent(history=history, user_message=body.message)
        try:
            _save_cloud_history(session_id, list(result.get("history", history))[-HISTORY_LIMIT:])
        except Exception:
            raise HTTPException(status_code=503, detail="Riwayat chat tidak dapat disimpan") from None
    else:
        with _state_lock:
            if not _allow_request(session_id, client_ip, now):
                raise HTTPException(status_code=429, detail=RATE_LIMIT_REPLY)
            state = _get_session(session_id, now)

        with state.lock:
            result = run_agent(history=list(state.history), user_message=body.message)
            state.history = list(result.get("history", state.history))[-HISTORY_LIMIT:]
            with _state_lock:
                state.last_active = time.monotonic()

    tool_calls = result.get("tool_calls", [])
    return {
        "reply": result.get("reply", ""),
        "tools": [call.get("name", "") for call in tool_calls if isinstance(call, dict)],
    }


@app.get("/staff/tickets")
def get_staff_tickets(request: Request) -> list[dict[str, Any]]:
    """Return open tickets to authenticated staff."""
    _authorize_staff(request)
    _verify_shared_storage()
    return list_open_tickets()


@app.post("/staff/tickets/{ticket_id}/close")
def post_close_ticket(
    request: Request,
    ticket_id: int = ApiPath(gt=0),
) -> dict[str, bool]:
    """Close an open ticket after staff authentication."""
    _authorize_staff(request)
    _verify_shared_storage()
    if not close_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan atau sudah ditutup")
    return {"closed": True}


frontend_path = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_path, html=True, check_dir=False), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8001")),
    )
