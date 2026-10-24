"""Test script to verify Gemini API connection using google-genai SDK.

Sends a single greeting prompt to the configured Gemini model using credentials
from environment variables loaded via python-dotenv.
Never prints or logs secret API keys.
"""

import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env without reading or opening the file directly
load_dotenv()


def main() -> None:
    """Send a single prompt to Gemini and print the response or sanitized error."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        print("Error (ValueError): GEMINI_API_KEY tidak ditemukan di environment variable.")
        return

    clean_api_key = api_key.strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

    prompt = "Halo, perkenalkan dirimu dalam satu kalimat"
    print(f"Mengirim pesan ke model: {model_name}")
    print(f"Prompt: {prompt!r}")
    print("-" * 50)

    try:
        client = genai.Client(api_key=clean_api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )

        answer = response.text
        print("Jawaban model:")
        print(answer)
    except Exception as exc:
        error_type = exc.__class__.__name__
        raw_msg = str(exc)
        # Redact any accidental leakage of the API key in error messages or URLs
        sanitized_msg = raw_msg.replace(clean_api_key, "[REDACTED_API_KEY]")
        print(f"Error ({error_type}): {sanitized_msg}")


if __name__ == "__main__":
    main()
