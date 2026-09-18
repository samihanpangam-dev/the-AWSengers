"""
backend/main.py — FastAPI entrypoint for the Omni-File AI Agent v2.

Architecture:
- AWS Cedar Policy Engine authorization gating on all requests.
- Strands Agent initialized with local Qwen 2.5 via Ollama.
- Bound to guaranteed prebuilt media tools (PyMuPDF & ffmpeg-python).
- Concurrency protection via asyncio.Lock().
- Multipart/form-data upload and file download serving.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from strands import Agent

from .config import ACTIVE_MODEL, ENV, UPLOAD_TMP_DIR, get_model
from .media_tools import ALL_MEDIA_TOOLS, get_artifacts, reset_artifacts
from .security import cedar_engine

# ── Response Models ───────────────────────────────────────────────────────────

class ProcessResponse(BaseModel):
    response: str = Field(description="Assistant text response.")
    files: list[str] = Field(default_factory=list, description="Array of generated file download paths/URLs.")
    download_url: str | None = Field(default=None, description="Primary download URL for backward compatibility.")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Strands Agent Initialization (Qwen 2.5 via Ollama) ────────────────────────

AGENT_SYSTEM_PROMPT = """
You are the Omni-File Agent. You have a suite of dedicated tools for media and PDF operations:
- merge_pdfs(input_paths, output_path): Merges ANY number of PDF files (2, 3, 5, 10+) into one. You must pass ALL input file paths in the input_paths list.
- split_pdf_to_zip(input_path, output_dir): Splits a PDF into individual pages and zips them.
- extract_pdf_text(input_path): Extracts all text from a PDF.
- compress_pdf(input_path, output_path): Compresses a PDF file.
- convert_media(input_path, output_path): Converts audio or video to a new format based on output extension.
- extract_audio(input_video, output_audio): Strips video track and saves only audio.
- trim_media(input_path, output_path, start_time, end_time): Trims media using HH:MM:SS or SS timestamps.
- compress_video(input_path, output_path, crf): Compresses a video to reduce file size.

When a user requests a file operation, you MUST use the provided tools. You are STRICTLY FORBIDDEN from generating or executing raw Python scripts for these standard tasks. Execute the tool silently.

Response instructions:
Always return a brief, friendly confirmation message of what was done.
Tag each generated file path in your message, like:
[OUTPUT: /path/to/file1.mp4]
[OUTPUT: /path/to/file2.wav]

Or return a valid JSON object with "message" and "files", like:
{"message": "I processed your files.", "files": ["/path/to/file1.mp4", "/path/to/file2.wav"]}
CRITICAL: Never output empty commas or placeholders like [ , ] in JSON.
""".strip()

agent = Agent(
    model=get_model(),
    system_prompt=AGENT_SYSTEM_PROMPT,
    tools=ALL_MEDIA_TOOLS,
)

agent_lock = asyncio.Lock()

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Omni-File AI Agent",
    description=(
        "Enterprise file-transformation agent powered by Strands, "
        "AWS Cedar policy engine, and prebuilt PyMuPDF & FFmpeg tools."
    ),
    version="2.1.0",
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
        f"3. When trimming media or converting, ensure the output path is distinct from the input path.\n"
        f"4. Tag every created output file with [OUTPUT: <absolute_path>] (e.g. [OUTPUT: {tmp_dir}/filename]) or return a JSON object with 'message' and 'files'.\n"
        f"5. Never output empty commas or placeholders like [ , ] in JSON."
    )


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


@app.post("/process", tags=["agent"], response_model=ProcessResponse)
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
) -> ProcessResponse:
    """
    Main agent endpoint:
    1. Persists uploaded files to isolated temp directory.
    2. Enforces AWS Cedar authorization policies (guardrail.cedar).
    3. Invokes Strands Agent under asyncio.Lock concurrency guard.
    4. Detects output files and returns clean assistant message and download URLs array.
    """
    request_id = str(uuid.uuid4())
    tmp_dir = Path(UPLOAD_TMP_DIR) / request_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    reset_artifacts()

    logger.info(
        "request=%s  env=%s  files=%d  prompt=%r",
        request_id, ENV, len(files), prompt[:120],
    )

    saved: list[tuple[str, str]] = []

    try:
        # ── 1. Persist uploads to temp directory ──────────────────────────────
        def _save_upload(upload_file, dest_path):
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)

        for upload in files:
            safe_name = Path(upload.filename or "unnamed").name
            dest = tmp_dir / safe_name
            await asyncio.to_thread(_save_upload, upload, dest)
            saved.append((safe_name, str(dest)))
            logger.info(
                "request=%s  saved %s (%d bytes)",
                request_id, safe_name, dest.stat().st_size,
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

        async def _run_safely():
            async with agent_lock:
                return await asyncio.to_thread(agent, enriched)

        agent_task = asyncio.create_task(_run_safely())

        async def _watch_disconnect():
            while True:
                if await request.is_disconnected():
                    logger.warning("request=%s  client disconnected! Aborting...", request_id)
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

        # ── 5. Detect and extract generated output files ──────────────────────
        parsed_message: str | None = None
        candidate_paths: list[str] = []

        # 5a. Attempt to parse JSON response if agent returned structured output
        json_pattern = (
            re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', response_text)
            or re.search(r'(\{[\s\S]*?"message"[\s\S]*?"files"[\s\S]*?\})', response_text)
            or re.search(r'(\{[\s\S]*?"files"[\s\S]*?"message"[\s\S]*?\})', response_text)
        )
        if json_pattern:
            try:
                raw_json = json_pattern.group(1)
                data = json.loads(raw_json)
                if isinstance(data, dict):
                    if "message" in data and isinstance(data["message"], str):
                        parsed_message = data["message"]
                    if "files" in data:
                        if isinstance(data["files"], list):
                            candidate_paths.extend([str(p).strip() for p in data["files"] if str(p).strip()])
                        elif isinstance(data["files"], str) and data["files"].strip():
                            candidate_paths.append(data["files"].strip())
            except Exception as e:
                logger.warning("request=%s  JSON parse failed, applying regex extraction: %s", request_id, e)

        # 5b. Robust fallback if json.loads failed (e.g. malformed JSON like empty commas in array)
        if not parsed_message:
            msg_match = re.search(r'"message"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', response_text)
            if msg_match:
                try:
                    parsed_message = json.loads(f'"{msg_match.group(1)}"')
                except Exception:
                    parsed_message = msg_match.group(1)

        # Extract any valid quoted file paths from a "files": [ ... ] block even if malformed
        files_block_match = re.search(r'"files"\s*:\s*\[([\s\S]*?)\]', response_text)
        if files_block_match:
            for path in re.findall(r'"([^"]+)"', files_block_match.group(1)):
                if path.strip() and path.strip() not in candidate_paths:
                    candidate_paths.append(path.strip())

        # 5c. Match any [OUTPUT: /path/to/file] tags in text
        output_matches = re.findall(r'\[OUTPUT:\s*([^\]]+)\]', response_text)
        for tag_path in output_matches:
            if tag_path.strip() and tag_path.strip() not in candidate_paths:
                candidate_paths.append(tag_path.strip())

        # Clean up response text for display
        response_text = re.sub(r'\[OUTPUT:\s*[^\]]+\]', '', response_text)
        response_text = re.sub(r'```[\s\S]*?```', '', response_text)
        response_text = re.sub(rf"{re.escape(str(tmp_dir))}/[^\s\"'`]+", "", response_text)
        # Strip any raw JSON envelope { ... } if left in response_text
        if "{" in response_text and "}" in response_text:
            response_text = re.sub(r'\{[\s\S]*?\}', '', response_text)
        response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()

        final_response_text = parsed_message if parsed_message else response_text

        # 5c. Identify newly created files on disk (excluding original input files)
        new_files = [
            f for f in tmp_dir.iterdir()
            if f.is_file()
            and f not in initial_files
            and f.resolve() not in input_paths
            and f.suffix != ".py"
            and not f.name.endswith(".py")
        ]
        # Sort newest files first
        new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # 5d. Resolve and validate output files from:
        # 1) Direct tool execution tracker (100% ground truth)
        # 2) LLM tagged candidate paths
        # 3) Newly created files on disk in tmp_dir
        tracked_artifacts = get_artifacts()
        logger.info("request=%s  directly tracked tool artifacts: %s", request_id, tracked_artifacts)

        resolved_files: list[Path] = []
        resolved_names: set[str] = set()

        # Priority 1: Files directly recorded by executed tools
        for art_path in tracked_artifacts:
            try:
                cand = Path(art_path).resolve()
                if cand.is_file() and cand not in input_paths and cand.name not in resolved_names:
                    resolved_files.append(cand)
                    resolved_names.add(cand.name)
            except Exception as ex:
                logger.warning("request=%s  failed resolving tracked artifact %r: %s", request_id, art_path, ex)

        # Priority 2: Candidates parsed from agent response (JSON or tags)
        for raw_p in candidate_paths:
            try:
                cand = Path(raw_p).resolve()
                if not cand.is_file():
                    cand = (tmp_dir / Path(raw_p).name).resolve()
                if cand.is_file() and str(cand).startswith(str(tmp_dir.resolve())):
                    if cand not in input_paths and cand.name not in resolved_names:
                        resolved_files.append(cand)
                        resolved_names.add(cand.name)
            except Exception as ex:
                logger.warning("request=%s  failed resolving candidate path %r: %s", request_id, raw_p, ex)

        # Priority 3: Any other newly created files in tmp_dir
        for nf in new_files:
            if nf.name not in resolved_names:
                resolved_files.append(nf.resolve())
                resolved_names.add(nf.name)

        # If files were successfully generated, sanitize apologetic or confusing LLM chatter
        if resolved_files:
            apology_patterns = [
                r"\bi apologize\b",
                r"\blet'?s try this step-by-step\b",
                r"\bi'?m sorry\b",
                r"\bsorry for the confusion\b",
                r"\bthere was an error\b",
                r"\blet me try again\b",
            ]
            has_apology = any(re.search(pat, final_response_text, re.IGNORECASE) for pat in apology_patterns)
            if has_apology or len(final_response_text.strip()) < 5:
                file_names = ", ".join(f.name for f in resolved_files)
                final_response_text = f"Successfully generated: {file_names}."

        download_urls = [f"/download/{request_id}/{f.name}" for f in resolved_files]
        primary_download = download_urls[0] if download_urls else None

        logger.info(
            "request=%s  completed with %d output files: %s",
            request_id,
            len(download_urls),
            [f.name for f in resolved_files],
        )

        return ProcessResponse(
            response=final_response_text or "Task completed successfully.",
            files=download_urls,
            download_url=primary_download,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("request=%s  unexpected agent error", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {exc}",
        ) from exc


@app.get("/download/{request_id}/{filename}", tags=["agent"])
async def download_file(request_id: str, filename: str):
    """Download a file generated by the agent."""
    path = Path(UPLOAD_TMP_DIR) / request_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename, content_disposition_type="attachment")
