"""Offline tests for TokoBantu's FastAPI endpoints."""

import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ["PYTHON_DOTENV_DISABLED"] = "true"

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import app.main as main_module
import app.tools.escalation as escalation_module


class ApiTests(unittest.TestCase):
    """Exercise validation, in-memory state, limits, and staff access."""

    def setUp(self) -> None:
        """Reset in-memory state and create an isolated test client."""
        with main_module._state_lock:
            main_module._sessions.clear()
            main_module._request_times.clear()
        self.client = TestClient(main_module.app)

    def tearDown(self) -> None:
        """Close the test client after each test."""
        self.client.close()

    @staticmethod
    def fake_agent(history: list[dict[str, str]], user_message: str) -> dict[str, object]:
        """Return a deterministic response without calling Gemini or Shopify."""
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "model", "content": "Balasan tiruan"},
        ]
        return {
            "reply": "Balasan tiruan",
            "history": updated_history,
            "tool_calls": [{"name": "search_products", "args": {}, "result": {}}],
        }

    def test_invalid_uuid_returns_422(self) -> None:
        """Reject a session identifier that is not a UUID."""
        response = self.client.post("/chat", json={"session_id": "bukan-uuid", "message": "Halo"})
        self.assertEqual(response.status_code, 422)

    def test_message_over_1000_characters_returns_422(self) -> None:
        """Reject messages longer than the public API limit."""
        response = self.client.post(
            "/chat",
            json={"session_id": str(uuid4()), "message": "x" * 1001},
        )
        self.assertEqual(response.status_code, 422)

    def test_rate_limit_is_per_session_and_per_ip(self) -> None:
        """Block the 21st message for a session and independently for an IP."""
        with patch.object(main_module, "run_agent", side_effect=self.fake_agent):
            session_id = str(uuid4())
            for _ in range(20):
                response = self.client.post(
                    "/chat", json={"session_id": session_id, "message": "Halo"}
                )
                self.assertEqual(response.status_code, 200)
            limited_session = self.client.post(
                "/chat", json={"session_id": session_id, "message": "Halo"}
            )
            self.assertEqual(limited_session.status_code, 429)

            with main_module._state_lock:
                main_module._request_times.clear()
            for _ in range(20):
                response = self.client.post(
                    "/chat", json={"session_id": str(uuid4()), "message": "Halo"}
                )
                self.assertEqual(response.status_code, 200)
            limited_ip = self.client.post(
                "/chat", json={"session_id": str(uuid4()), "message": "Halo"}
            )
            self.assertEqual(limited_ip.status_code, 429)
            self.assertIn("Silakan coba lagi", limited_ip.json()["detail"])

    def test_agent_failure_returns_safe_message_and_logs_only_exception_type(self) -> None:
        """Avoid a generic 500 while excluding exception text from logs."""
        private_marker = "customer@example.com"
        with patch.dict(os.environ, {"VERCEL": "", "TOKOBANTU_STORAGE_MODE": ""}), patch.object(
            main_module, "run_agent", side_effect=RuntimeError(private_marker)
        ), self.assertLogs(main_module.logger, level="ERROR") as captured:
            response = self.client.post(
                "/chat", json={"session_id": str(uuid4()), "message": "Tolong cek"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Layanan AI sedang tidak tersedia")
        self.assertIn("RuntimeError", "\n".join(captured.output))
        self.assertNotIn(private_marker, "\n".join(captured.output))

    def test_missing_gemini_key_returns_safe_configuration_message(self) -> None:
        """Make a missing Gemini key diagnosable without exposing a secret."""
        with patch.dict(os.environ, {"VERCEL": "", "TOKOBANTU_STORAGE_MODE": ""}), patch.object(
            main_module,
            "run_agent",
            side_effect=ValueError("GEMINI_API_KEY environment variable is missing or empty."),
        ):
            response = self.client.post(
                "/chat", json={"session_id": str(uuid4()), "message": "Tolong cek"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Layanan AI belum dikonfigurasi")

    def test_hosted_chat_reports_missing_database_configuration(self) -> None:
        """Explain the hosted persistent database requirement without exposing config."""
        env = {
            "VERCEL": "1",
            "TOKOBANTU_STORAGE_MODE": "",
            "TOKOBANTU_DATABASE_URL": "",
            "DATABASE_URL": "",
            "STORAGE_URL": "",
            "RATE_LIMIT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env), patch.object(
            main_module, "_allow_cloud_request", side_effect=RuntimeError("no database")
        ):
            response = self.client.post(
                "/chat", json={"session_id": str(uuid4()), "message": "Halo"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database persisten belum dikonfigurasi")

    def test_neon_storage_url_is_used_by_chat_and_ticket_storage(self) -> None:
        """Accept the STORAGE_URL name shown by Vercel's Neon connect dialog."""
        with patch.dict(
            os.environ,
            {
                "TOKOBANTU_DATABASE_URL": "",
                "DATABASE_URL": "",
                "STORAGE_URL": "postgresql://test.invalid/db",
            },
        ):
            self.assertEqual(main_module._database_url(), "postgresql://test.invalid/db")
            self.assertEqual(escalation_module._database_url(), "postgresql://test.invalid/db")

    def test_staff_requires_authorization(self) -> None:
        """Reject requests with no staff header or a wrong token."""
        with patch.dict(os.environ, {"STAFF_TOKEN": "test-secret"}), patch.object(
            main_module, "list_open_tickets", return_value=[]
        ):
            missing = self.client.get("/staff/tickets")
            incorrect = self.client.get(
                "/staff/tickets", headers={"Authorization": "Bearer wrong-secret"}
            )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(incorrect.status_code, 401)

    def test_staff_accepts_correct_token(self) -> None:
        """Return open tickets when the configured bearer token is correct."""
        tickets = [{"id": 1, "status": "open"}]
        with patch.dict(os.environ, {"STAFF_TOKEN": "test-secret"}), patch.object(
            main_module, "list_open_tickets", return_value=tickets
        ):
            response = self.client.get(
                "/staff/tickets", headers={"Authorization": "Bearer test-secret"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), tickets)

    def test_staff_disabled_when_token_is_empty(self) -> None:
        """Return service unavailable when no staff token is configured."""
        with patch.dict(os.environ, {"STAFF_TOKEN": ""}):
            response = self.client.get("/staff/tickets")
        self.assertEqual(response.status_code, 503)

    def test_vercel_staff_storage_must_be_configured(self) -> None:
        """Do not silently use ephemeral SQLite for hosted Vercel tickets."""
        with patch.dict(os.environ, {"VERCEL": "1", "STAFF_TOKEN": "test-secret"}), patch.object(
            main_module, "_database_url", return_value=""
        ):
            response = self.client.get(
                "/staff/tickets", headers={"Authorization": "Bearer test-secret"}
            )
        self.assertEqual(response.status_code, 503)

    def test_staff_can_close_ticket(self) -> None:
        """Forward an authenticated close request to the ticket tool."""
        with patch.dict(os.environ, {"STAFF_TOKEN": "test-secret"}), patch.object(
            main_module, "close_ticket", return_value=True
        ) as close_mock:
            response = self.client.post(
                "/staff/tickets/42/close",
                headers={"Authorization": "Bearer test-secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"closed": True})
        close_mock.assert_called_once_with(42)

    def test_health_endpoint_remains_available(self) -> None:
        """Keep the health endpoint independent from staff authentication."""
        with patch.dict(os.environ, {"VERCEL": "", "TOKOBANTU_STORAGE_MODE": ""}):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_hosted_health_requires_database_configuration(self) -> None:
        """Expose missing persistent storage as not ready in hosted mode."""
        with patch.dict(os.environ, {"VERCEL": "1", "TOKOBANTU_STORAGE_MODE": "postgres"}), patch.object(
            main_module, "_database_url", return_value=""
        ):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database persisten belum dikonfigurasi")

    def test_hosted_health_checks_database_connection(self) -> None:
        """Return ready only after a hosted database can execute a query."""
        connection = MagicMock()
        connection.__enter__.return_value = connection
        with patch.dict(os.environ, {"VERCEL": "1", "TOKOBANTU_STORAGE_MODE": "postgres"}), patch.object(
            main_module, "_database_url", return_value="postgresql://test"
        ), patch.object(main_module, "_connect_cloud_database", return_value=connection):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        connection.execute.assert_called_once_with("SELECT 1")
        connection.commit.assert_called_once_with()

    def test_hosted_health_reports_database_unavailable(self) -> None:
        """Avoid reporting ready when hosted Postgres cannot be reached."""
        with patch.dict(os.environ, {"VERCEL": "1", "TOKOBANTU_STORAGE_MODE": "postgres"}), patch.object(
            main_module, "_database_url", return_value="postgresql://test"
        ), patch.object(main_module, "_connect_cloud_database", side_effect=RuntimeError("offline")):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database persisten tidak tersedia")

    def test_health_storage_error_log_sanitizes_connection_details(self) -> None:
        """Log database failures without full URLs, credentials, email, or tokens."""
        error_message = (
            "connect failed postgres://dbuser:dbpass@db.example/orders "
            "postgresql://dbuser2:dbpass2@db2.example/orders "
            "password=hiddenpass user=hiddenuser customer@example.com "
            "Bearer bearer-secret token=api-secret "
            + "x" * 400
        )
        with patch.dict(os.environ, {"VERCEL": "1", "TOKOBANTU_STORAGE_MODE": "postgres"}), patch.object(
            main_module, "_database_url", return_value="postgresql://not-logged.example/db"
        ), patch.object(
            main_module, "_connect_cloud_database", side_effect=RuntimeError(error_message)
        ), self.assertLogs(main_module.logger, level="ERROR") as captured:
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        log_message = "\n".join(captured.output)
        self.assertIn("RuntimeError", log_message)
        self.assertIn("[REDACTED_DATABASE_URL]", log_message)
        self.assertIn("password=[REDACTED]", log_message)
        self.assertIn("user=[REDACTED]", log_message)
        for sensitive_value in (
            "postgres://dbuser:dbpass@db.example/orders",
            "postgresql://dbuser2:dbpass2@db2.example/orders",
            "hiddenpass",
            "hiddenuser",
            "customer@example.com",
            "bearer-secret",
            "api-secret",
            "not-logged.example",
        ):
            self.assertNotIn(sensitive_value, log_message)
        sanitized_message = log_message.split("): ", maxsplit=1)[1]
        self.assertLessEqual(len(sanitized_message), 300)

    def test_ticket_storage_error_log_sanitizes_connection_details(self) -> None:
        """Keep ticket database errors useful without logging connection secrets."""
        error_message = "failed postgres://dbuser:dbpass@db.example/tickets user=privateuser"
        with patch.dict(
            os.environ,
            {"VERCEL": "1", "TOKOBANTU_DATABASE_URL": "postgresql://not-logged.example/db"},
        ), patch.object(
            escalation_module, "_connect", side_effect=RuntimeError(error_message)
        ), self.assertLogs(escalation_module.logger, level="ERROR") as captured:
            result = escalation_module.create_escalation_ticket(
                summary="Barang rusak",
                reason="damaged_item",
                urgency="medium",
                order_number="#1234",
                contact="customer@example.com",
            )

        self.assertFalse(result["ok"])
        log_message = "\n".join(captured.output)
        self.assertIn("RuntimeError", log_message)
        self.assertIn("[REDACTED_DATABASE_URL]", log_message)
        self.assertNotIn("postgres://dbuser:dbpass@db.example/tickets", log_message)
        self.assertNotIn("privateuser", log_message)
        self.assertNotIn("customer@example.com", log_message)

    def test_frontend_is_served_from_root(self) -> None:
        """Serve the customer chat page from the static root mount."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("TokoBantu", response.text)

    def test_staff_frontend_is_served_as_static_file(self) -> None:
        """Serve the separate staff interface from the frontend directory."""
        response = self.client.get("/staff.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("panel tiket", response.text)

    def test_expired_session_starts_with_empty_history(self) -> None:
        """Forget history after 30 minutes without accepted activity."""
        observed_histories: list[list[dict[str, str]]] = []

        def recording_agent(history: list[dict[str, str]], user_message: str) -> dict[str, object]:
            """Record model inputs and return a deterministic turn."""
            observed_histories.append(list(history))
            return self.fake_agent(history, user_message)

        session_id = str(uuid4())
        with patch.object(main_module, "run_agent", side_effect=recording_agent):
            first = self.client.post(
                "/chat", json={"session_id": session_id, "message": "Pertama"}
            )
            self.assertEqual(first.status_code, 200)
            with main_module._state_lock:
                main_module._sessions[session_id].last_active = (
                    time.monotonic() - main_module.SESSION_TTL_SECONDS - 1
                )
            second = self.client.post(
                "/chat", json={"session_id": session_id, "message": "Kedua"}
            )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(observed_histories[0], [])
        self.assertEqual(observed_histories[1], [])

    def test_cloud_history_is_pruned_and_capped(self) -> None:
        """Enforce expiry and the 500-session limit in shared storage."""
        connection = MagicMock()
        connection.__enter__.return_value = connection
        with patch.object(main_module, "_connect_cloud_database", return_value=connection), patch.object(
            main_module, "_ensure_cloud_tables"
        ):
            main_module._save_cloud_history(
                str(uuid4()),
                [{"role": "user", "content": str(index)} for index in range(25)],
            )

        queries = [call.args[0] for call in connection.execute.call_args_list]
        params = [call.args[1] if len(call.args) > 1 else None for call in connection.execute.call_args_list]
        self.assertTrue(any("pg_advisory_xact_lock" in query for query in queries))
        self.assertTrue(any("DELETE FROM chat_sessions" in query and "last_active" in query for query in queries))
        cap_index = next(
            index for index, query in enumerate(queries)
            if "DELETE FROM chat_sessions WHERE session_id IN" in query
        )
        self.assertIn("OFFSET %s", queries[cap_index])
        self.assertEqual(params[cap_index], (main_module.SESSION_LIMIT,))
        insert_index = next(index for index, query in enumerate(queries) if "INSERT INTO chat_sessions" in query)
        saved_history = __import__("json").loads(params[insert_index][1])
        self.assertEqual(len(saved_history), main_module.HISTORY_LIMIT)
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
