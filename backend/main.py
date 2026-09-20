"""
backend/main.py — FastAPI entrypoint for the Omni-File AI Agent.

Architecture:
- AWS Cedar Policy Engine authorization gating on all requests (guardrail.cedar).
- Strands Agent initialized with local Qwen 2.5 via Ollama.
- Bound to guaranteed prebuilt media tools (PyMuPDF & ffmpeg-python).
- Concurrency protection via asyncio.Lock().
- Multipart/form-data upload and file download serving.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import (
    ACTIVE_MODEL,
    BILLING_CHECKOUT_URL,
    ENV,
    MAX_PROMPT_LENGTH,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_FILES,
    SUBSCRIPTION_WEBHOOK_SECRET,
    TEMP_RETENTION_SECONDS,
    UPLOAD_TMP_DIR,
    get_model,
)
from .media_tools import ALL_MEDIA_TOOLS
from .security import cedar_engine
from .subscriptions import subscription_store

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    ".pdf", ".mp3", ".mp4", ".wav", ".m4a", ".aac", ".avi",
    ".mov", ".mkv", ".flac", ".ogg",
}

# ── Strands Agent Configuration (Qwen 2.5 via Ollama / Bedrock) ───────────────

AGENT_SYSTEM_PROMPT = """
You are the Omni-File Agent. You have a suite of dedicated tools for media and PDF operations. When a user requests a file operation, you MUST use the provided tools. You are STRICTLY FORBIDDEN from generating or executing raw Python scripts for these standard tasks. Execute the tool silently, and return only the final output file path and a brief success message.

Available Tools:
- merge_pdfs(input_paths, output_path): Merges multiple PDF files into one. Pass ALL input file paths in input_paths.
- split_pdf_to_zip(input_path, output_dir): Splits a PDF into individual pages and zips them into pages.zip.
- extract_pdf_text(input_path): Extracts all text from a PDF document.
- compress_pdf(input_path, output_path): Compresses a PDF file to reduce size.
- convert_media(input_path, output_path): Converts audio or video to a new format based on output extension.
- extract_audio(input_video, output_audio): Strips video track and saves only audio.
- trim_media(input_path, output_path, start_time, end_time): Trims media using HH:MM:SS or SS timestamps.
- compress_video(input_path, output_path, crf): Compresses a video to reduce file size.
- inspect_media(input_path): Inspects media metadata using ffprobe.

Format rule: Always wrap the final generated output file path in your reply formatted exactly as:
[OUTPUT: /absolute/path/to/file]
""".strip()

try:
    from strands import Agent
    agent = Agent(
        model=get_model(),
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=ALL_MEDIA_TOOLS,
    )
    logger.info("Strands Agent initialized with model %s and %d tools", ACTIVE_MODEL, len(ALL_MEDIA_TOOLS))
except Exception as exc:
    logger.warning("Strands Agent could not be initialized at startup (%s). Using fallback handler.", exc)
    agent = None

agent_lock = asyncio.Lock()

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Omni-File AI Agent",
    description=(
        "Enterprise file-transformation agent powered by Strands, "
        "AWS Cedar policy engine, and prebuilt PyMuPDF & FFmpeg tools."
    ),
    version="2.2.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

logger.info("CORS: allow_origins=* — tunnel/Vercel mode")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_enriched_prompt(prompt: str, saved: list[tuple[str, str]], tmp_dir: Path) -> str:
    """Injects file paths and output directory guidance for tool invocation."""
    if not saved:
        return prompt

    file_lines = "\n".join(f"  • {name} → {path}" for name, path in saved)
    return (
        f"{prompt}\n\n"
        f"Working Directory: {tmp_dir}\n"
        f"Files available on disk:\n"
        f"{file_lines}\n\n"
        f"Instructions:\n"
        f"1. Call the appropriate prebuilt tool to perform the request.\n"
        f"2. Ensure output files are saved into the working directory: {tmp_dir}\n"
        f"3. When trimming media, ensure the output path is distinct from the input path.\n"
        f"4. Respond with a brief friendly message and the output path in [OUTPUT: <path>]."
    )


def _cleanup_stale_requests() -> None:
    """Remove abandoned request folders left when a client never downloads output."""
    root = Path(UPLOAD_TMP_DIR)
    if not root.is_dir():
        return
    cutoff = time.time() - TEMP_RETENTION_SECONDS
    for request_dir in root.iterdir():
        try:
            if request_dir.is_dir() and request_dir.stat().st_mtime < cutoff:
                shutil.rmtree(request_dir, ignore_errors=True)
        except OSError:
            logger.warning("Unable to inspect temporary request directory %s", request_dir)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe confirming service and model status."""
    return {
        "status": "ok",
        "env": ENV,
        "model": ACTIVE_MODEL,
        "security": "AWS Cedar Policy Engine",
        "tools": "Hardcoded Media & PDF Tools",
    }


def _user_id(request: Request) -> str:
    value = request.headers.get("X-User-ID", "dev-user").strip()
    if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=400, detail="Invalid X-User-ID")
    return value


@app.get("/subscription/status", tags=["subscription"])
async def subscription_status(request: Request) -> dict[str, Any]:
    return subscription_store.status(_user_id(request)).as_dict()


@app.post("/subscription/subscribe", tags=["subscription"])
async def subscribe(request: Request) -> dict[str, Any]:
    return subscription_store.activate(_user_id(request)).as_dict()


@app.post("/subscription/checkout", tags=["subscription"])
async def checkout(request: Request) -> dict[str, Any]:
    """Return a configured provider checkout URL, or activate the dev plan."""
    user_id = _user_id(request)
    if BILLING_CHECKOUT_URL:
        separator = "&" if "?" in BILLING_CHECKOUT_URL else "?"
        return {
            "checkout_url": f"{BILLING_CHECKOUT_URL}{separator}{urlencode({'user_id': user_id})}",
            "provider": subscription_store.status(user_id).provider,
        }
    if subscription_store.status(user_id).provider == "dev":
        return subscription_store.activate(user_id).as_dict()
    raise HTTPException(
        status_code=503,
        detail="Billing checkout is not configured",
    )


@app.post("/subscription/webhook", tags=["subscription"])
async def subscription_webhook(request: Request) -> dict[str, Any]:
    if SUBSCRIPTION_WEBHOOK_SECRET and not hmac.compare_digest(
        request.headers.get("X-Webhook-Secret", ""), SUBSCRIPTION_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str) or not isinstance(payload.get("user_id"), str):
        raise HTTPException(status_code=400, detail="Webhook requires event and user_id")
    return subscription_store.apply_webhook(payload["user_id"], payload["event"]).as_dict()


@app.post("/process", tags=["agent"])
async def process(
    request: Request,
    prompt: str = Form(
        ...,
        description="Natural-language instruction for the agent.",
    ),
    files: list[UploadFile] = File(
        default=[],
        description="One or more files to transform.",
    ),
) -> dict[str, Any]:
    """
    Main agent endpoint:
    1. Persists uploaded files to isolated temp directory.
    2. Enforces AWS Cedar authorization policies (guardrail.cedar).
    3. Invokes Strands Agent under asyncio.Lock concurrency guard.
    4. Detects output files and returns clean assistant message and download URL.
    """
    try:
        subscription_store.require_access(_user_id(request))
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise HTTPException(status_code=413, detail=f"Prompt exceeds {MAX_PROMPT_LENGTH} characters")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"No more than {MAX_UPLOAD_FILES} files may be uploaded")

    _cleanup_stale_requests()
    request_id = str(uuid.uuid4())
    tmp_dir = Path(UPLOAD_TMP_DIR) / request_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "request=%s  env=%s  files=%d  prompt=%r",
        request_id, ENV, len(files), prompt[:120],
    )

    saved: list[tuple[str, str]] = []

    try:
        # ── 1. Persist uploads to temp directory ──────────────────────────────
        def _save_upload(upload_file, dest_path):
            total = 0
            with open(dest_path, "wb") as f:
                while chunk := upload_file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise ValueError(f"File exceeds {MAX_UPLOAD_BYTES} bytes")
                    f.write(chunk)
            return total

        for upload in files:
            safe_name = Path(upload.filename or "unnamed").name
            extension = Path(safe_name).suffix.lower()
            if not safe_name or extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=415, detail=f"Unsupported file type: {safe_name or 'unnamed'}")
            if any(existing_name == safe_name for existing_name, _ in saved):
                raise HTTPException(status_code=400, detail=f"Duplicate filename: {safe_name}")
            dest = tmp_dir / safe_name
            try:
                size = await asyncio.to_thread(_save_upload, upload, dest)
            except ValueError as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            saved.append((safe_name, str(dest)))
            logger.info(
                "request=%s  saved %s (%d bytes)",
                request_id, safe_name, size,
            )

        input_paths = {Path(dest).resolve() for _, dest in saved}
        initial_files = set(tmp_dir.iterdir())

        # ── 2. AWS Cedar Policy Authorization Gate ────────────────────────────
        filenames = [name for name, _ in saved]
        cedar_decision = cedar_engine.classify_and_evaluate(prompt, filenames)
        logger.info(
            "request=%s  Cedar policy evaluation: allowed=%s action=%s diagnostics=%s",
            request_id, cedar_decision.allowed, cedar_decision.action, cedar_decision.diagnostics,
        )

        if not cedar_decision.allowed:
            logger.warning("request=%s  Cedar authorization BLOCKED: %s", request_id, cedar_decision.diagnostics)
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden by AWS Cedar policy: {cedar_decision.diagnostics}",
            )

        # ── 3. Enrich prompt with file paths ──────────────────────────────────
        enriched = _build_enriched_prompt(prompt, saved, tmp_dir)

        # ── 4. Run the Strands Agent with Lock & Disconnect Watcher ───────────
        logger.info("request=%s  invoking agent with prebuilt media tools…", request_id)

        if agent is None:
            raise RuntimeError("Strands Agent is not initialized. Ensure strands-agents is installed.")

        async def _run_safely():
            async with agent_lock:
                return await asyncio.to_thread(agent, enriched)

        agent_task = asyncio.create_task(_run_safely())

        async def _watch_disconnect():
            while True:
                if await request.is_disconnected():
                    logger.warning("request=%s  client disconnected! Aborting...", request_id)
                    if hasattr(agent, "cancel"):
                        agent.cancel()
                    agent_task.cancel()
                    break
                await asyncio.sleep(1)

        watcher_task = asyncio.create_task(_watch_disconnect())

        try:
            result = await agent_task
        except asyncio.CancelledError:
            raise
        finally:
            watcher_task.cancel()

        response_text = str(result)
        logger.info("request=%s  agent replied (%d chars)", request_id, len(response_text))

        # ── 5. Detect and extract generated output file ───────────────────────
        download_url = None

        # Clean up any leaked markdown code blocks or JSON traces
        response_text = re.sub(r'```[\s\S]*?```', '', response_text)

        # Identify newly created files on disk (excluding original input files)
        new_files = [
            f for f in tmp_dir.iterdir()
            if f.is_file()
            and f not in initial_files
            and f.resolve() not in input_paths
            and f.suffix.lower() in ALLOWED_EXTENSIONS
        ]
        new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Match [OUTPUT: /tmp/omni_agent/<uuid>/filename]
        match = re.search(r'\[OUTPUT:\s*([^\]]+)\]', response_text)
        matched_file = None
        if match:
            raw_path = match.group(1).strip()
            response_text = response_text.replace(match.group(0), "")
            try:
                candidate = Path(raw_path).resolve()
                if (
                    candidate.is_file()
                    and tmp_dir.resolve() in candidate.parents
                    and candidate.suffix.lower() in ALLOWED_EXTENSIONS
                ):
                    if candidate not in input_paths:
                        matched_file = candidate
                    else:
                        logger.warning(
                            "request=%s  agent output tag pointed to original input file %s",
                            request_id, candidate.name,
                        )
            except Exception as e:
                logger.warning("request=%s  failed resolving tagged path %r: %s", request_id, raw_path, e)

        if matched_file:
            download_url = f"/download/{request_id}/{matched_file.name}"
            logger.info("request=%s  selected tagged output file: %s", request_id, matched_file.name)
        elif new_files:
            output_file = new_files[0]
            download_url = f"/download/{request_id}/{output_file.name}"
            logger.info("request=%s  detected new output file on disk: %s", request_id, output_file.name)
        else:
            logger.info("request=%s  no output file generated (text query or informational reply)", request_id)

        # Fallback: remove residual /tmp/omni_agent/... paths leaked in message
        response_text = re.sub(rf"{re.escape(str(tmp_dir))}/[^\s\"'`]+", "", response_text)
        response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()

        if download_url is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"response": response_text, "download_url": download_url}

    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("request=%s  unexpected agent error", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {exc}",
        ) from exc


@app.get("/download/{request_id}/{filename}", tags=["agent"])
async def download_file(request_id: str, filename: str):
    """Download a file generated by the agent."""
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid request id") from exc
    request_dir = Path(UPLOAD_TMP_DIR) / str(request_uuid)
    safe_name = Path(filename).name
    path = (request_dir / safe_name).resolve()
    if path.parent != request_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        filename=safe_name,
        content_disposition_type="attachment",
        background=BackgroundTask(shutil.rmtree, request_dir, ignore_errors=True),
    )
