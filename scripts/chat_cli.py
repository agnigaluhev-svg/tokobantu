"""Interactive terminal chat interface for TokoBantu customer service agent.

Connects to Gemini through run_agent in app.agent using live credentials
loaded from environment variables via python-dotenv.
Never opens, reads, or prints the contents of .env.
"""

import os
from pathlib import Path
import sys
from typing import Any

# Enable ANSI escape sequences on Windows console if needed
os.system("")

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment variables without reading or opening .env directly
load_dotenv()

from app.agent import run_agent

# ANSI color codes
GRAY = "\033[90m"
RESET = "\033[0m"
MAX_HISTORY_ITEMS = 20


def main() -> None:
    """Run interactive conversation loop with TokoBantu CS agent."""
    print("=" * 60)
    print("TokoBantu Demo - Obrolan Interaktif Customer Service")
    print("Ketik 'exit' atau tekan Ctrl+C untuk keluar.")
    print("=" * 60)
    print()

    history: list[dict[str, Any]] = []

    while True:
        try:
            user_input = input("Anda: ")
        except (KeyboardInterrupt, EOFError):
            print("\nSampai jumpa!")
            break

        clean_input = user_input.strip()
        if clean_input.lower() == "exit":
            print("Sampai jumpa!")
            break

        if not clean_input:
            continue

        print("TokoBantu sedang mengetik...")
        try:
            result = run_agent(history=history, user_message=clean_input)
            reply = result.get("reply", "")
            history = result.get("history", [])

            # Keep conversation history bounded to the last 20 messages
            if len(history) > MAX_HISTORY_ITEMS:
                history = history[-MAX_HISTORY_ITEMS:]

            print(f"TokoBantu: {reply}")

            # Print gray tool usage indicator containing only tool names
            tool_calls = result.get("tool_calls", [])
            tool_names = [call.get("name") for call in tool_calls if call.get("name")]
            tool_summary = ", ".join(tool_names) if tool_names else "tidak ada"
            print(f"{GRAY}[tool: {tool_summary}]{RESET}\n")

        except KeyboardInterrupt:
            print("\nKeluar...")
            break
        except Exception:
            # Catch unexpected runtime exceptions without printing stack traces or keys
            print("Terjadi kesalahan, coba lagi\n")


if __name__ == "__main__":
    main()
