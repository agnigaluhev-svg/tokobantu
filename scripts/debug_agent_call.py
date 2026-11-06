"""Debug script to test Gemini API call variations against live model.

Tests four configuration variants (tools vs thinking_config) with a single
prompt, measuring latency and diagnosing model response behavior without retries.
Never prints or leaks secrets or .env contents.
"""

import os
from pathlib import Path
import re
import sys
import time
from typing import Any

from dotenv import load_dotenv
from google.genai import types

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.agent import TOOL_FUNCTIONS, get_default_client
from app.prompts import SYSTEM_PROMPT

# Load environment variables without reading or opening .env directly
load_dotenv()


def sanitize(text: str) -> str:
    """Replace API keys and secrets in any text with [REDACTED].

    Args:
        text: Input string that might contain sensitive keys.

    Returns:
        Sanitized string safe for terminal output.
    """
    if not text:
        return ""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
    if shopify_token:
        text = text.replace(shopify_token, "[REDACTED]")
    # Redact query params like key=...
    text = re.sub(r"(key=)[a-zA-Z0-9_\-]+", r"\1[REDACTED]", text)
    return text


def run_variant(
    variant_name: str,
    client: Any,
    model_name: str,
    contents: list[types.Content],
    config: types.GenerateContentConfig,
) -> None:
    """Execute a single model call for a given variant and print the result.

    Args:
        variant_name: Human-readable variant identifier and description.
        client: Configured Gemini client instance.
        model_name: Name of the Gemini model.
        contents: Formatted prompt contents list.
        config: Generation configuration to test.
    """
    print("\n==================================================")
    print(f"Varian: {variant_name}")

    start_time = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
        duration_sec = time.perf_counter() - start_time
        print(f"Lama   : {duration_sec:.2f} detik")

        function_calls = getattr(response, "function_calls", None)
        if function_calls:
            func_names = [getattr(fc, "name", "unknown") for fc in function_calls]
            print(f"Hasil  : OK (Fungsi yang diminta: {', '.join(func_names)})")
        else:
            try:
                raw_text = getattr(response, "text", "") or ""
            except Exception:
                raw_text = ""
            preview = sanitize(raw_text)[:80]
            print(f"Hasil  : OK (Teks: {preview!r})")

    except Exception as exc:
        duration_sec = time.perf_counter() - start_time
        print(f"Lama   : {duration_sec:.2f} detik")

        error_class = exc.__class__.__name__

        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code is None and hasattr(exc, "response"):
            status_code = getattr(exc.response, "status_code", None)

        status_str = f", Kode Status HTTP: {status_code}" if status_code is not None else ""

        raw_err_msg = str(exc)
        sanitized_err_msg = sanitize(raw_err_msg)[:300]

        print(f"Hasil  : GAGAL ({error_class}{status_str})")
        print(f"Error  : {sanitized_err_msg}")


def main() -> None:
    """Run all four Gemini call variants sequentially."""
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    client = get_default_client()

    prompt_message = "ada snowboard apa aja?"
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_message)],
        )
    ]
    tools_list = list(TOOL_FUNCTIONS.values())

    # Varian A: tanpa tool dan tanpa thinking_config
    config_a = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        http_options=types.HttpOptions(timeout=30000),
    )

    # Varian B: hanya thinking_config (level LOW)
    config_b = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        http_options=types.HttpOptions(timeout=30000),
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )

    # Varian C: hanya deklarasi tool
    config_c = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools_list,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=30000),
    )

    # Varian D: tool dan thinking_config sekaligus (sama seperti agent)
    config_d = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools_list,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=30000),
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )

    variants = [
        ("A) Tanpa tool dan tanpa thinking_config", config_a),
        ("B) Hanya thinking_config (level LOW)", config_b),
        ("C) Hanya deklarasi tool", config_c),
        ("D) Tool dan thinking_config sekaligus (sama seperti agent)", config_d),
    ]

    print("Memulai pengujian 4 varian panggilan Gemini...")
    print(f"Model  : {model_name}")
    print(f"Pesan  : {prompt_message!r}")

    for name, cfg in variants:
        run_variant(name, client, model_name, contents, cfg)

    print("\n==================================================")
    print("Pengujian selesai.")


if __name__ == "__main__":
    main()
