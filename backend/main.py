"""
backend/main.py — FastAPI entrypoint for the Omni-File AI Agent v2.

Endpoints
---------
GET  /health   — liveness probe; exposes active ENV and model ID so operators
                 can confirm which mode is running after a deploy.
POST /process  — multipart/form-data: prompt (str) + files[] (UploadFile[])
                 → JSON { "response": str }

Run locally
-----------
    source .venv/bin/activate
    uvicorn backend.main:app --reload --port 8000

Docker
------
    docker run -e ENV=production -p 8000:8000 omni-agent
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import ACTIVE_MODEL, ENV, UPLOAD_TMP_DIR, apply_guardrail
from .guardrail import GuardrailException
from .agent import agent

agent_lock = asyncio.Lock()

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
        "A dynamic file-transformation agent powered by Strands. "
        "Synthesizes and executes custom Python scripts for any file operation."
    ),
    version="2.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# allow_origins=["*"] + allow_credentials=False so that:
#   • The Vercel frontend (arbitrary *.vercel.app subdomain) is never blocked.
#   • Teammates' browsers behind any origin work without configuration.
#   • The Cloudflare tunnel URL doesn't need to be hardcoded here.
#
# To lock down for production: replace ["*"] with ["https://your-app.vercel.app"]
# and set allow_credentials=True.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

logger.info("CORS: allow_origins=* — tunnel/Vercel mode")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_enriched_prompt(prompt: str, saved: list[tuple[str, str]]) -> str:
    """
    Inject absolute file paths into the user prompt so the agent's synthesized
    scripts can hard-code them without guessing.

    The separator line "Files saved to disk:" is the exact string the system
    prompt tells the LLM to look for in STEP 1 of its workflow.
    """
    if not saved:
        return prompt

    file_lines = "\n".join(f"  • {name} → {path}" for name, path in saved)
    return (
        f"{prompt}\n\n"
        f"Files saved to disk:\n"
        f"{file_lines}\n\n"
        f"Use the exact absolute paths above in your synthesized script."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """
    Liveness probe — returns immediately without touching the agent.

    The response includes the active ENV and model so operators can confirm
    the correct mode is running after a deploy or container restart.
    """
    return {
        "status": "ok",
        "env":    ENV,
        "model":  ACTIVE_MODEL,
    }


from typing import Any
from fastapi import Request

@app.post("/process", tags=["agent"])
async def process(
    request: Request,
    prompt: str = Form(
        ...,
        description="Natural-language instruction for the agent.",
    ),
    files: list[UploadFile] = File(
        default=[],
        description=(
            "One or more files to transform. "
            "Optional — the agent handles text-only queries too."
        ),
    ),
) -> dict[str, Any]:
    """
    Main agent endpoint.

    Accepts multipart/form-data with:
      prompt  — the user's natural-language request.
      files   — zero or more uploaded files (PDF, MP4, MP3, image, …).

    Returns
    -------
    {"response": str, "download_url": str | None}
        The agent's natural-language reply, including output file path(s).

    Error responses
    ---------------
    400  GuardrailException  — synthesized code blocked by safety guardrail.
    500  Unexpected error    — agent or subprocess raised an unhandled exception.
    """
    request_id = str(uuid.uuid4())
    tmp_dir = Path(UPLOAD_TMP_DIR) / request_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "request=%s  env=%s  files=%d  prompt=%r",
        request_id, ENV, len(files), prompt[:120],
    )

    saved: list[tuple[str, str]] = []

    try:
        # ── 1. Persist uploads to an isolated temp directory ──────────────────
        import asyncio
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

        # ── 2. Enrich prompt with absolute file paths ─────────────────────────
        enriched = _build_enriched_prompt(prompt, saved)

        # ── 3. Pre-flight guardrail scan on the raw prompt ────────────────────
        # Catches secrets / injection strings in the user's message itself,
        # before the agent ever runs. The agent's check_guardrail @tool handles
        # synthesized code; this gate handles the prompt layer.
        preflight = apply_guardrail(prompt)
        if preflight["action"] == "GUARDRAIL_INTERVENED":
            pattern = preflight.get("detected_pattern", "policy violation")
            logger.warning(
                "request=%s  pre-flight guardrail blocked — pattern=%r",
                request_id, pattern,
            )
            raise GuardrailException(
                reason=f"Prompt blocked by safety guardrail: {pattern}",
                detected_pattern=pattern,
            )

        # ── 4. Run the Strands Agent ──────────────────────────────────────────
        logger.info("request=%s  invoking agent…", request_id)
        
        async def _run_safely():
            async with agent_lock:
                return await asyncio.to_thread(agent, enriched)
                
        agent_task = asyncio.create_task(_run_safely())
        
        async def _watch_disconnect():
            while True:
                if await request.is_disconnected():
                    logger.warning("request=%s  client disconnected! Aborting...", request_id)
                    # 1. Kill any active code interpreter subprocesses (ffmpeg)
                    from .agent import kill_all_processes
                    kill_all_processes()
                    # 2. Cancel the agent's internal LLM loop
                    agent.cancel()
                    # 3. Cancel the wrapper task so the lock is released
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
        logger.info(
            "request=%s  agent replied (%d chars)",
            request_id, len(response_text),
        )
        
        # ── 5. Detect and extract generated output file ───────────────────────
        import re
        download_url = None
        
        # Clean up any leaked markdown code blocks or JSON traces
        response_text = re.sub(r'```[\s\S]*?```', '', response_text)
        
        # Identify any newly created files on disk (excluding scripts and input files)
        new_files = [
            f for f in tmp_dir.iterdir()
            if f.is_file()
            and f not in initial_files
            and f.resolve() not in input_paths
            and f.suffix != ".py"
            and not f.name.endswith(".py")
        ]
        new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Match [OUTPUT: /tmp/omni_agent/<uuid>/filename]
        match = re.search(r'\[OUTPUT:\s*([^\]]+)\]', response_text)
        matched_file = None
        if match:
            raw_path = match.group(1).strip()
            # Clean up the raw tag from response text
            response_text = response_text.replace(match.group(0), "")
            try:
                candidate = Path(raw_path).resolve()
                if candidate.is_file() and str(candidate).startswith(str(tmp_dir.resolve())):
                    # Reject if the agent accidentally pointed back to an input file
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
            # Fallback: agent generated a new file on disk but didn't tag it properly
            output_file = new_files[0]
            download_url = f"/download/{request_id}/{output_file.name}"
            logger.info("request=%s  detected new output file on disk: %s", request_id, output_file.name)
        else:
            logger.warning("request=%s  no new output file was generated in %s", request_id, tmp_dir)
                
        # Fallback: remove any residual /tmp/omni_agent/... paths the agent might have leaked
        response_text = re.sub(rf"{re.escape(str(tmp_dir))}/[^\s\"'`]+", "", response_text)
        
        # Clean up excessive newlines caused by stripping
        response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()
        
        return {"response": response_text, "download_url": download_url}

    except GuardrailException as exc:
        logger.warning(
            "request=%s  guardrail blocked — pattern=%r",
            request_id, exc.detected_pattern,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Guardrail blocked: {exc.reason}",
        ) from exc

    except Exception as exc:  # noqa: BLE001
        logger.exception("request=%s  unexpected agent error", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {exc}",
        ) from exc

    finally:
        # ── 5. Defer cleanup ───────────────────────────────────────────
        # We leave the tmp_dir so the user can download the output file.
        # A cron job or ephemeral container lifecycle will clean it up.
        pass

@app.get("/download/{request_id}/{filename}", tags=["agent"])
async def download_file(request_id: str, filename: str):
    """Download a file generated by the agent."""
    from fastapi.responses import FileResponse
    path = Path(UPLOAD_TMP_DIR) / request_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename, content_disposition_type="attachment")
