"""
Centralised configuration for the Omni-File AI Agent backend.
All tuneable values live here so nothing is hardcoded in business logic.
"""

# ── LLM ──────────────────────────────────────────────────────────────────────
# Local Ollama model — avoids cloud-API latency during development.
# Requires: `ollama pull llama3` to be run once before starting the server.
OLLAMA_MODEL: str = "ollama/llama3"
OLLAMA_BASE_URL: str = "http://localhost:11434"

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow the v0.dev / Next.js dev server on either default port.
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:3001",
]

# ── File Handling ─────────────────────────────────────────────────────────────
# Base directory for per-request temp uploads.  Each request gets its own
# UUID-named subdirectory which is cleaned up after the response is sent.
UPLOAD_TMP_DIR: str = "/tmp/omni_agent"
