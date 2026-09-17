"""
FastAPI entrypoint for the Omni-File AI Agent.

Endpoints
---------
GET  /health      — liveness probe; used by the React frontend to detect
                    whether the backend is reachable before sending files.
POST /process     — multipart/form-data: prompt (str) + files[] (UploadFile[])
                    → JSON { "response": str }

Run locally
-----------
    uvicorn backend.main:app --reload --port 8000

Or from inside the backend/ directory:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, UPLOAD_TMP_DIR
from .guardrail import GuardrailException
from .agent import agent

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Omni-File AI Agent",
    description=(
        "A file-transformation agent powered by Strands, Ollama, and "
        "Amazon Bedrock AgentCore."
    ),
    version="0.1.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the v0.dev / Next.js dev server to call this API from the browser.

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

logger.info("CORS enabled for origins: %s", CORS_ORIGINS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_enriched_prompt(prompt: str, saved_paths: list[tuple[str, str]]) -> str:
    """
    Augment the raw user prompt with the on-disk file context so the agent
    can reference actual paths when calling tools.

    Parameters
    ----------
    prompt : str
        The original natural-language request from the user.
    saved_paths : list[tuple[str, str]]
        List of (original_filename, absolute_disk_path) tuples.

    Returns
    -------
    str
        An enriched prompt string ready to be passed to the Strands Agent.
    """
    file_lines = "\n".join(
        f"  • {name}  →  {path}" for name, path in saved_paths
    )
    return (
        f"{prompt}\n\n"
        f"The following files have been uploaded and saved to disk:\n"
        f"{file_lines}\n\n"
        f"Use the file paths above when calling any tool."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe — returns immediately without touching the agent."""
    return {"status": "ok"}


@app.post("/process", tags=["agent"])
async def process(
    prompt: str = Form(..., description="Natural-language instruction for the agent."),
    files: list[UploadFile] = File(
        default=[],
        description="One or more files to process.  Optional — the agent can "
                    "answer text-only questions too.",
    ),
) -> dict[str, str]:
    """
    Main agent endpoint.

    Accepts a multipart/form-data body with:
    - ``prompt``  — the user's natural-language request.
    - ``files``   — zero or more uploaded files.

    Returns
    -------
    {"response": str}
        The agent's textual reply.

    Error responses
    ---------------
    400  GuardrailException — generated code was blocked by the safety guardrail.
    500  Unexpected error   — agent or tool raised an unhandled exception.
    """
    # ── 1. Create an isolated temp directory for this request ─────────────────
    request_id = str(uuid.uuid4())
    tmp_dir = Path(UPLOAD_TMP_DIR) / request_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "request=%s  prompt=%r  files=%d  tmp=%s",
        request_id,
        prompt[:80],
        len(files),
        tmp_dir,
    )

    saved_paths: list[tuple[str, str]] = []

    try:
        # ── 2. Persist each uploaded file to the temp directory ───────────────
        for upload in files:
            # Sanitise filename — strip any path components sent by the client.
            safe_name = Path(upload.filename or "unnamed").name
            dest = tmp_dir / safe_name
            content = await upload.read()
            dest.write_bytes(content)
            saved_paths.append((safe_name, str(dest)))
            logger.info(
                "request=%s  saved %s (%d bytes)",
                request_id,
                safe_name,
                len(content),
            )

        # ── 3. Build an enriched prompt that includes on-disk paths ───────────
        enriched = _build_enriched_prompt(prompt, saved_paths)

        # ── 4. Run the Strands Agent ──────────────────────────────────────────
        logger.info("request=%s  invoking agent …", request_id)
        result = agent(enriched)

        # Strands Agent returns an AgentResult; coerce to string for the JSON.
        response_text = str(result)
        logger.info(
            "request=%s  agent replied (%d chars)", request_id, len(response_text)
        )

        return {"response": response_text}

    except GuardrailException as exc:
        logger.warning("request=%s  guardrail blocked: %s", request_id, exc.reason)
        raise HTTPException(
            status_code=400,
            detail=f"Guardrail blocked execution: {exc.reason}",
        ) from exc

    except Exception as exc:  # noqa: BLE001
        logger.exception("request=%s  unexpected agent error", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {exc}",
        ) from exc

    finally:
        # ── 5. Always clean up the temp directory ─────────────────────────────
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info("request=%s  cleaned up %s", request_id, tmp_dir)
