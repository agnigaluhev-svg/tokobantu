"""Automated unit test suite for TokoBantu customer service agent loop.

Tests agent logic completely offline using mock responses (no internet or real API calls):
(a) Model directly answers with text
(b) Model calls search_products then answers
(c) Model calls get_order_status with unprovided email (must be blocked by guard)
(d) Model calls tools continuously (must terminate at 6 rounds)
(e) 503 error twice then success (recovers via retry)
(f) Continuous 503 error (exhausts retries and returns polite apology)
(g) Empty message and message > 1000 characters rejected

Never prints any secrets or tokens.
"""

from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.agent import (
    EMPTY_MESSAGE_REPLY,
    LOOP_EXCEEDED_REPLY,
    TOO_LONG_MESSAGE_REPLY,
    TRANSIENT_ERROR_REPLY,
    run_agent,
)


class FakeFunctionCall:
    """Mock Gemini FunctionCall object."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args


class FakeResponse:
    """Mock Gemini GenerateContentResponse object."""

    def __init__(
        self,
        text: str | None = None,
        function_calls: list[FakeFunctionCall] | None = None,
    ) -> None:
        self.text = text
        self.function_calls = function_calls or []


class FakeModels:
    """Mock Gemini client.models service."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.call_count = 0
        self.recorded_calls: list[dict[str, Any]] = []

    def generate_content(
        self,
        model: str,
        contents: Any,
        config: Any = None,
    ) -> Any:
        self.recorded_calls.append({
            "model": model,
            "contents": contents,
            "config": config,
        })
        if self.call_count >= len(self.responses):
            raise RuntimeError(
                f"FakeModels: Received call #{self.call_count + 1}, but only {len(self.responses)} responses configured."
            )
        resp = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


class FakeClient:
    """Mock Gemini Client container."""

    def __init__(self, responses: list[Any]) -> None:
        self.models = FakeModels(responses)


def print_case_result(case_id: str, title: str, passed: bool, detail: str) -> None:
    """Print formatted result for a test case."""
    status = "LULUS" if passed else "GAGAL"
    print(f"--- Kasus ({case_id}): {title} ---")
    print(f"Hasil      : [{status}] {detail}")
    print()


def main() -> None:
    """Execute all test cases for run_agent using mock responses."""
    print("=" * 65)
    print("UJI COBA RUN_AGENT DENGAN MOCK MODEL (OFFLINE)")
    print("=" * 65)
    print()

    total_passed = 0
    total_tests = 7
    fast_retries = (0.0, 0.0, 0.0)

    # (a) Model langsung menjawab teks
    fake_client_a = FakeClient([
        FakeResponse(text="Halo! Ada yang bisa saya bantu di TokoBantu Demo?"),
    ])
    res_a = run_agent(
        history=[],
        user_message="Halo",
        client=fake_client_a,
        retry_delays=fast_retries,
    )
    passed_a = (
        res_a.get("reply") == "Halo! Ada yang bisa saya bantu di TokoBantu Demo?"
        and len(res_a.get("tool_calls", [])) == 0
        and len(res_a.get("history", [])) == 2
    )
    detail_a = f"reply={res_a.get('reply')!r}, tool_calls={len(res_a.get('tool_calls', []))}"
    print_case_result("a", "Model langsung menjawab teks", passed_a, detail_a)
    if passed_a:
        total_passed += 1

    # (b) Model meminta search_products lalu menjawab
    fake_client_b = FakeClient([
        FakeResponse(
            function_calls=[
                FakeFunctionCall(name="search_products", args={"query": "snowboard"})
            ]
        ),
        FakeResponse(text="Kami menemukan produk snowboard di katalog kami."),
    ])
    res_b = run_agent(
        history=[],
        user_message="Cari snowboard dong",
        client=fake_client_b,
        retry_delays=fast_retries,
    )
    passed_b = (
        len(res_b.get("tool_calls", [])) == 1
        and res_b.get("tool_calls", [])[0]["name"] == "search_products"
        and res_b.get("reply") == "Kami menemukan produk snowboard di katalog kami."
    )
    detail_b = (
        f"tools_called={[t['name'] for t in res_b.get('tool_calls', [])]}, "
        f"reply={res_b.get('reply')!r}"
    )
    print_case_result("b", "Model meminta search_products lalu menjawab", passed_b, detail_b)
    if passed_b:
        total_passed += 1

    # (c) Model meminta get_order_status dengan email yang tidak pernah diketik pengguna
    fake_client_c = FakeClient([
        FakeResponse(
            function_calls=[
                FakeFunctionCall(
                    name="get_order_status",
                    args={"order_number": "#1001", "email": "hacker@example.com"},
                )
            ]
        ),
        FakeResponse(text="Bisa tolong sebutkan email pemesan Anda?"),
    ])
    res_c = run_agent(
        history=[],
        user_message="Cek status order #1001",
        client=fake_client_c,
        retry_delays=fast_retries,
    )
    guard_blocked = (
        len(res_c.get("tool_calls", [])) == 1
        and res_c.get("tool_calls", [])[0]["result"] == {
            "ok": False,
            "error": "Email belum diberikan pelanggan",
        }
    )
    passed_c = guard_blocked and bool(res_c.get("reply"))
    detail_c = (
        f"guard_result={res_c.get('tool_calls', [])[0]['result'] if res_c.get('tool_calls') else None}, "
        f"reply={res_c.get('reply')!r}"
    )
    print_case_result("c", "get_order_status diblokir guard karena email tidak ada di chat", passed_c, detail_c)
    if passed_c:
        total_passed += 1

    # (d) Model terus-menerus meminta tool, harus berhenti di 6 putaran
    infinite_tool_responses = [
        FakeResponse(
            function_calls=[
                FakeFunctionCall(name="get_store_policy", args={"topic": "returns"})
            ]
        )
        for _ in range(8)
    ]
    fake_client_d = FakeClient(infinite_tool_responses)
    res_d = run_agent(
        history=[],
        user_message="Tanya retur",
        client=fake_client_d,
        retry_delays=fast_retries,
    )
    passed_d = (
        len(res_d.get("tool_calls", [])) == 6
        and res_d.get("reply") == LOOP_EXCEEDED_REPLY
    )
    detail_d = f"total_rounds={len(res_d.get('tool_calls', []))}, reply={res_d.get('reply')!r}"
    print_case_result("d", "Loop berhenti tepat pada 6 putaran tool", passed_d, detail_d)
    if passed_d:
        total_passed += 1

    # (e) Error 503 dua kali lalu berhasil, harus lolos lewat retry
    fake_client_e = FakeClient([
        RuntimeError("503 Service Unavailable"),
        RuntimeError("503 Service Unavailable"),
        FakeResponse(text="Halo, saya siap membantu setelah pulih."),
    ])
    res_e = run_agent(
        history=[],
        user_message="Halo",
        client=fake_client_e,
        retry_delays=fast_retries,
    )
    passed_e = (
        fake_client_e.models.call_count == 3
        and res_e.get("reply") == "Halo, saya siap membantu setelah pulih."
    )
    detail_e = f"attempts={fake_client_e.models.call_count}, reply={res_e.get('reply')!r}"
    print_case_result("e", "Error 503 dua kali lalu berhasil (retry backoff)", passed_e, detail_e)
    if passed_e:
        total_passed += 1

    # (f) 503 terus-menerus, harus memberi reply sopan
    fake_client_f = FakeClient([
        RuntimeError("503 Service Unavailable"),
        RuntimeError("503 Service Unavailable"),
        RuntimeError("503 Service Unavailable"),
        RuntimeError("503 Service Unavailable"),
    ])
    res_f = run_agent(
        history=[],
        user_message="Halo",
        client=fake_client_f,
        retry_delays=fast_retries,
    )
    passed_f = (
        fake_client_f.models.call_count == 4
        and res_f.get("reply") == TRANSIENT_ERROR_REPLY
    )
    detail_f = f"attempts={fake_client_f.models.call_count}, reply={res_f.get('reply')!r}"
    print_case_result("f", "503 terus-menerus menghasilkan permohonan maaf sopan", passed_f, detail_f)
    if passed_f:
        total_passed += 1

    # (g) Pesan kosong dan pesan lebih dari 1000 karakter ditolak
    fake_client_g = FakeClient([])
    res_g_empty = run_agent(
        history=[],
        user_message="   ",
        client=fake_client_g,
        retry_delays=fast_retries,
    )
    res_g_long = run_agent(
        history=[],
        user_message="a" * 1001,
        client=fake_client_g,
        retry_delays=fast_retries,
    )
    passed_g = (
        fake_client_g.models.call_count == 0
        and res_g_empty.get("reply") == EMPTY_MESSAGE_REPLY
        and res_g_long.get("reply") == TOO_LONG_MESSAGE_REPLY
    )
    detail_g = (
        f"empty_reply={res_g_empty.get('reply')!r}, "
        f"long_reply={res_g_long.get('reply')!r}, "
        f"calls_to_model={fake_client_g.models.call_count}"
    )
    print_case_result("g", "Pesan kosong dan > 1000 karakter ditolak", passed_g, detail_g)
    if passed_g:
        total_passed += 1

    total_failed = total_tests - total_passed
    print("=" * 65)
    print("RINGKASAN UJI COBA")
    print("=" * 65)
    print(f"Total kasus : {total_tests}")
    print(f"Lulus       : {total_passed}")
    print(f"Gagal       : {total_failed}")
    print("=" * 65)


if __name__ == "__main__":
    main()
