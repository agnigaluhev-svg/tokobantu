"""Customer service agent orchestrator for TokoBantu.

Manages Gemini conversational model interactions, manual tool-calling loop,
retry mechanisms, security guards, and audit logging.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.prompts import SYSTEM_PROMPT
from app.tools.escalation import create_escalation_ticket
from app.tools.orders import get_order_status
from app.tools.policy import get_store_policy
from app.tools.products import get_stock, search_products

# Load environment variables without reading or printing .env directly
load_dotenv()

# Log file path for tool calls
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE_PATH = LOGS_DIR / "tool_calls.jsonl"

# Standard tool definitions
TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "search_products": search_products,
    "get_stock": get_stock,
    "get_order_status": get_order_status,
    "get_store_policy": get_store_policy,
    "create_escalation_ticket": create_escalation_ticket,
}

MAX_TOOL_ROUNDS = 6
MAX_MESSAGE_LENGTH = 1000

TRANSIENT_ERROR_REPLY = "Maaf, layanan kami sedang ramai. Silakan coba lagi sebentar lagi."
LOOP_EXCEEDED_REPLY = "Maaf, permintaan Anda memerlukan terlalu banyak langkah untuk diproses. Silakan hubungi staf toko kami."
EMPTY_MESSAGE_REPLY = "Pesan tidak boleh kosong."
TOO_LONG_MESSAGE_REPLY = "Pesan terlalu panjang (maksimal 1000 karakter)."


def get_default_client() -> genai.Client:
    """Create a default Gemini client using environment variables.

    Returns:
        Configured genai.Client instance.

    Raises:
        ValueError: If GEMINI_API_KEY is not set or empty.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing or empty.")
    return genai.Client(api_key=api_key)


def _log_tool_call(
    tool_name: str,
    args: dict[str, Any],
    ok: bool,
    duration_sec: float,
) -> None:
    """Record a tool execution to logs/tool_calls.jsonl.

    Records only parameter names, never values, customer messages, or tokens.

    Args:
        tool_name: Name of the executed tool.
        args: Dictionary of arguments passed to the tool.
        ok: Whether the tool completed successfully.
        duration_sec: Execution duration in seconds.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "parameter_names": sorted(list(args.keys())),
            "ok": ok,
            "duration_seconds": duration_sec,
        }
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")
    except Exception:
        # Logging failures should not interrupt customer service responses
        pass


def _extract_user_texts(history: list[Any], user_message: str) -> list[str]:
    """Extract all text content sent by human users from history and current message.

    Args:
        history: Conversation history list.
        user_message: Current user input string.

    Returns:
        List of user message strings.
    """
    texts: list[str] = [user_message]
    for item in history:
        if isinstance(item, dict):
            role = item.get("role", "")
            if role in ("user", "human"):
                content = item.get("content")
                if isinstance(content, str):
                    texts.append(content)
                parts = item.get("parts")
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            texts.append(part["text"])
                        elif hasattr(part, "text") and getattr(part, "text", None):
                            texts.append(getattr(part, "text"))
        elif hasattr(item, "role") and getattr(item, "role") in ("user", "human"):
            parts = getattr(item, "parts", [])
            for part in parts:
                if hasattr(part, "text") and getattr(part, "text", None):
                    texts.append(getattr(part, "text"))
    return texts


def _is_email_provided_by_user(email: str, user_texts: list[str]) -> bool:
    """Check if the given email was explicitly provided in user messages.

    Args:
        email: Email address requested by the model.
        user_texts: List of user message texts.

    Returns:
        True if the email appears in any user message, False otherwise.
    """
    clean_target = email.strip().lower()
    if not clean_target:
        return False
    return any(clean_target in text.lower() for text in user_texts)


def _is_transient_error(exc: Exception) -> bool:
    """Determine whether an exception represents a transient/recoverable error.

    Args:
        exc: Exception instance.

    Returns:
        True if the error is temporary (503, 429, timeout), False otherwise.
    """
    msg = str(exc).lower()
    transient_indicators = [
        "503",
        "429",
        "timeout",
        "timed out",
        "deadline",
        "unavailable",
        "resource exhausted",
        "rate limit",
    ]
    if any(indicator in msg for indicator in transient_indicators):
        return True

    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code in (429, 503, 504):
        return True

    return False


def _call_model_with_retry(
    client: Any,
    model: str,
    contents: Any,
    config: Any,
    retry_delays: tuple[float, ...],
) -> Any:
    """Execute generate_content with backoff retries for transient errors.

    Args:
        client: Gemini client or fake mock client.
        model: Model name string.
        contents: Formatted contents payload.
        config: GenerateContentConfig instance.
        retry_delays: Sequence of sleep delays for each retry attempt.

    Returns:
        Model response object.

    Raises:
        Exception: If retries are exhausted or a non-transient error occurs.
    """
    attempts = len(retry_delays) + 1
    for attempt_idx in range(attempts):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            if not _is_transient_error(exc) or attempt_idx == attempts - 1:
                raise
            delay = retry_delays[attempt_idx]
            if delay > 0:
                time.sleep(delay)


def run_agent(
    history: list[Any],
    user_message: str,
    client: Any = None,
    retry_delays: tuple[float, ...] = (1.0, 2.0, 4.0),
) -> dict[str, Any]:
    """Execute customer service agent turn with tool orchestration and safety guards.

    Args:
        history: Prior conversation turns list.
        user_message: Current user prompt string.
        client: Optional Gemini client or mock client for testing.
        retry_delays: Delays in seconds between transient retry attempts.

    Returns:
        Dictionary with keys:
        - "reply": Final assistant message string.
        - "history": Updated conversation history list.
        - "tool_calls": List of all tool calls executed during this turn.
    """
    # 1. Validate user message constraints
    if not isinstance(user_message, str) or not user_message.strip():
        return {
            "reply": EMPTY_MESSAGE_REPLY,
            "history": history,
            "tool_calls": [],
        }

    if len(user_message) > MAX_MESSAGE_LENGTH:
        return {
            "reply": TOO_LONG_MESSAGE_REPLY,
            "history": history,
            "tool_calls": [],
        }

    clean_message = user_message.strip()

    # 2. Initialize Gemini client
    active_client = client if client is not None else get_default_client()
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

    # 3. Configure tools and disable automatic function calling for manual loop
    tools_list = list(TOOL_FUNCTIONS.values())
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools_list,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    # 4. Prepare contents structure
    contents: list[Any] = []
    for item in history:
        if isinstance(item, types.Content):
            contents.append(item)
        elif isinstance(item, dict):
            role = item.get("role", "user")
            content_str = item.get("content")
            if isinstance(content_str, str):
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content_str)],
                    )
                )
            elif "parts" in item:
                contents.append(item)

    # Append new user message
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=clean_message)],
        )
    )

    user_texts = _extract_user_texts(history, clean_message)
    accumulated_tool_calls: list[dict[str, Any]] = []
    round_count = 0
    final_reply = ""

    # 5. Manual tool execution loop (up to MAX_TOOL_ROUNDS iterations)
    while True:
        try:
            response = _call_model_with_retry(
                active_client,
                model_name,
                contents,
                config,
                retry_delays,
            )
        except Exception as exc:
            if _is_transient_error(exc):
                return {
                    "reply": TRANSIENT_ERROR_REPLY,
                    "history": history,
                    "tool_calls": accumulated_tool_calls,
                }
            raise

        function_calls = getattr(response, "function_calls", None)
        if not function_calls:
            # Model finished reasoning and returned text reply
            final_reply = getattr(response, "text", "") or ""
            break

        if round_count >= MAX_TOOL_ROUNDS:
            final_reply = LOOP_EXCEEDED_REPLY
            break

        round_count += 1
        round_results: list[tuple[str, Any]] = []

        for fc in function_calls:
            tool_name = getattr(fc, "name", "")
            raw_args = getattr(fc, "args", {})
            tool_args = dict(raw_args) if isinstance(raw_args, dict) else {}

            start_time = time.time()
            ok = True
            tool_result: Any = None

            if tool_name not in TOOL_FUNCTIONS:
                ok = False
                tool_result = {"ok": False, "error": f"Tool '{tool_name}' tidak dikenal"}
            elif tool_name == "get_order_status":
                email_arg = str(tool_args.get("email", "")).strip()
                if not _is_email_provided_by_user(email_arg, user_texts):
                    # Guard: Block execution if email was never typed by customer
                    ok = False
                    tool_result = {"ok": False, "error": "Email belum diberikan pelanggan"}
                else:
                    try:
                        tool_result = TOOL_FUNCTIONS[tool_name](**tool_args)
                        ok = tool_result.get("ok", True) if isinstance(tool_result, dict) else True
                    except Exception as exc:
                        ok = False
                        tool_result = {
                            "ok": False,
                            "error": f"Gagal mengeksekusi tool: {exc.__class__.__name__}",
                        }
            else:
                try:
                    tool_result = TOOL_FUNCTIONS[tool_name](**tool_args)
                    ok = tool_result.get("ok", True) if isinstance(tool_result, dict) else True
                except Exception as exc:
                    ok = False
                    tool_result = {
                        "ok": False,
                        "error": f"Gagal mengeksekusi tool: {exc.__class__.__name__}",
                    }

            duration_sec = round(time.time() - start_time, 4)
            _log_tool_call(tool_name, tool_args, ok, duration_sec)

            accumulated_tool_calls.append({
                "name": tool_name,
                "args": tool_args,
                "result": tool_result,
            })
            round_results.append((tool_name, tool_result))

        # Append model turn containing function calls to contents
        if (
            hasattr(response, "candidates")
            and response.candidates
            and hasattr(response.candidates[0], "content")
            and response.candidates[0].content
        ):
            contents.append(response.candidates[0].content)
        else:
            model_parts = [
                types.Part(
                    function_call=types.FunctionCall(
                        name=getattr(f, "name", ""),
                        args=dict(getattr(f, "args", {})),
                    )
                )
                for f in function_calls
            ]
            contents.append(types.Content(role="model", parts=model_parts))

        # Append tool execution results back to contents as user responses
        response_parts = [
            types.Part.from_function_response(
                name=t_name,
                response=t_res if isinstance(t_res, dict) else {"result": t_res},
            )
            for t_name, t_res in round_results
        ]
        contents.append(types.Content(role="user", parts=response_parts))

    # 6. Update conversation history
    updated_history = list(history) + [
        {"role": "user", "content": clean_message},
        {"role": "model", "content": final_reply},
    ]

    return {
        "reply": final_reply,
        "history": updated_history,
        "tool_calls": accumulated_tool_calls,
    }
