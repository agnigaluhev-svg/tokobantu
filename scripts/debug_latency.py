"""Debug: daftar model Gemini dan ukur lama respons (timeout 120 dtk)."""
import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY", "").strip()
if not api_key:
    raise SystemExit("GEMINI_API_KEY belum diisi")

mode = sys.argv[1] if len(sys.argv) > 1 else "list"


def redact(text: str) -> str:
    """Samarkan kunci API sebelum dicetak."""
    return text.replace(api_key, "[REDACTED]")


if mode == "list":
    client = genai.Client(api_key=api_key)
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            print(m.name)
elif mode == "time":
    model = sys.argv[2] if len(sys.argv) > 2 else os.getenv("GEMINI_MODEL", "")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120000))
    for i in (1, 2):
        start = time.time()
        try:
            resp = client.models.generate_content(
                model=model, contents="Sebutkan tiga jenis snowboard dalam satu kalimat."
            )
            print(f"{model} #{i}: OK {time.time() - start:.1f} dtk -> {(resp.text or '')[:60]}")
        except Exception as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            print(f"{model} #{i}: GAGAL {time.time() - start:.1f} dtk "
                  f"{exc.__class__.__name__} kode={code} -> {redact(str(exc))[:200]}")
else:
    print("Pakai: python scripts/debug_latency.py list | time <nama-model>")