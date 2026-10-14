from fastapi import FastAPI

app = FastAPI(title="TokoBantu")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint to verify server status."""
    return {"status": "ok"}
