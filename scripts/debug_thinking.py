"""Debug: bandingkan panggilan Gemini polos dengan yang memakai thinking LOW."""
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
if not api_key:
    raise SystemExit("GEMINI_API_KEY belum diisi")

client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30000))
prompt = "Sebutkan tiga jenis snowboard dalam satu kalimat singkat."


def redact(text: str) -> str:
    """Samarkan kunci API dari teks sebelum dicetak."""
    return text.replace(api_key, "[REDACTED]")


def run(name: str, config) -> None:
    """Panggil Gemini satu kali tanpa retry, lalu cetak hasil atau penyebab error."""
    start = time.time()
    try:
        resp = client.models.generate_content(model=model, contents=prompt, config=config)
        print(f"{name}: OK ({time.time() - start:.1f} dtk) -> {(resp.text or '')[:80]}")
    except Exception as exc:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        print(
            f"{name}: GAGAL ({time.time() - start:.1f} dtk) "
            f"{exc.__class__.__name__} kode={code} -> {redact(str(exc))[:300]}"
        )


run("A (polos)", None)
run(
    "B (thinking LOW)",
    types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    ),
)