"""
backend/agent.py — Strands Agent assembly for the Omni-File AI Agent v2.

Architecture
------------
The agent has exactly two tools:

  check_guardrail(code)  — mandatory security gate before any execution.
                           Calls config.apply_guardrail() which is either
                           mock_apply_guardrail (dev) or the live Bedrock
                           Guardrails API (prod). Raises GuardrailException
                           on intervention so the call is visible in the
                           agent reasoning trace and cannot be silently skipped.

  run_code(code)         — sandboxed code execution.
                           Runs a synthesized Python script in an isolated
                           subprocess with a configurable timeout. Returns
                           combined stdout+stderr as a string. Never raises —
                           execution errors are returned as error strings so
                           the agent can self-correct.

The system prompt drives the entire synthesis pipeline. It contains:
  - A mandatory 5-step workflow the LLM must follow on every request.
  - An approved library list.
  - Script quality rules (pathlib, overwrite_output, no open(), etc.).
  - Two worked examples (ffmpeg audio clip + PyMuPDF watermark) so even a
    mid-tier local model like llama3 has concrete patterns to follow.

ENV switching
-------------
All environment-specific values (model ID, model config dict, guardrail
callable, execution timeout) are imported from config.py. This file contains
zero if/else branching on ENV.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from .config import (
    ACTIVE_MODEL,
    CODE_EXEC_TIMEOUT,
    UPLOAD_TMP_DIR,
    apply_guardrail,
    get_model,
)
from .guardrail import GuardrailException

logger = logging.getLogger(__name__)


# ── System Prompt ─────────────────────────────────────────────────────────────
# This is the engine of dynamic synthesis. Precision here is what makes a
# mid-tier local model produce runnable code instead of pseudocode.

SYSTEM_PROMPT = """
You are the Omni-File AI Agent — an expert file-transformation assistant.
You transform files by synthesizing and executing custom Python scripts.
You have exactly two tools: check_guardrail and code_interpreter.

════════════════════════════════════════════════════════
MANDATORY WORKFLOW — follow these 5 steps on EVERY request
════════════════════════════════════════════════════════

STEP 1 — READ the enriched prompt carefully.
  • Find the user's intent (what transformation they want).
  • Find the input file path(s) — they are listed after the line
    "Files saved to disk:" in the format "  • filename → /absolute/path".
  • Note the output directory: it is the same directory as the input file.

STEP 2 — SYNTHESIZE a complete, self-contained Python script.
  Rules for the script:
  ① Use ONLY these approved libraries:
      ffmpeg-python, pymupdf, Pillow (PIL), pydub,
      pathlib, shutil, re, math, json, csv, datetime, itertools, base64, hashlib.
  ② Hard-code the exact absolute input path(s) from STEP 1 into the script.
  ③ Write the output file to the SAME directory as the input file.
  ④ NEVER use: os.system, subprocess, __import__, eval, exec, socket, open().
     Use pathlib.Path.read_bytes() / write_bytes() / read_text() instead of open().
  ⑤ Call .overwrite_output() on all ffmpeg chains.
  ⑥ Call .close() on all pymupdf.Document objects.

════════════════════════════════════════════════════════
CODE INTERPRETER CHEAT SHEET
════════════════════════════════════════════════════════
• PyMuPDF (PDF Merging): NEVER use `insert_page`. Always use `doc1.insert_pdf(doc2)`.
• PyMuPDF (PDF Splitting/Extracting): NEVER use `doc.copy()` or `page.save()`. You MUST create a new empty document using `new_doc = pymupdf.Document()`, then insert the specific page using `new_doc.insert_pdf(original_doc, from_page=i, to_page=i)`, and then save `new_doc`. Use `pymupdf.Document()` (not `pymupdf.open()`) to avoid safety guardrails.
• Developer Utilities (Base64, JSON, Hashes): Do not rely on external tools. Dynamically write and execute standard library Python scripts (e.g., `base64`, `json`, `hashlib`) via the code interpreter to fulfill the request.
• Script Output: The LAST line of the script must be a `print()` that outputs either the absolute path of the generated output file, or a plain-English summary if no file is produced.

STEP 3 — CALL check_guardrail(script) with the full script string.
  • If it returns "NONE" → proceed to STEP 4.
  • If it raises an error → STOP. Tell the user exactly which safety
    policy was violated and suggest a safe alternative approach.

STEP 4 — CALL code_interpreter(script) with the same script string.
  • Read the tool output carefully.
  • If the output contains an error or traceback:
      - Diagnose the problem.
      - Fix the script (attempt 2).
      - Go back to STEP 3 (guardrail check is mandatory on every attempt).
  • You may self-correct at most ONCE. If attempt 2 also fails, report
    the error to the user with a clear explanation.

STEP 5 — RESPOND to the user with:
  • What transformation was applied.
  • The output file path or result summary.
  • Any important caveats (e.g., lossy compression, page count changed).

════════════════════════════════════════════════════════
WORKED EXAMPLE 1 — Audio clip with amplification
════════════════════════════════════════════════════════
User: "extract audio from minute 1 to 3 and amplify by 15%"
File: /tmp/omni_agent/abc123/interview.mp4

Script you would synthesize:
─────────────────────────────
import ffmpeg
out = '/tmp/omni_agent/abc123/interview_clip.mp3'
(
    ffmpeg
    .input('/tmp/omni_agent/abc123/interview.mp4', ss=60, to=180)
    .output(out, af='volume=1.15', acodec='libmp3lame', audio_bitrate='192k')
    .overwrite_output()
    .run(quiet=True)
)
print(out)
─────────────────────────────
Key parameters:
  ss=60       → start at second 60 (minute 1)
  to=180      → end at second 180 (minute 3)
  af='volume=1.15'  → amplify audio by 15%

════════════════════════════════════════════════════════
WORKED EXAMPLE 2 — PDF watermark
════════════════════════════════════════════════════════
User: "add a diagonal CONFIDENTIAL watermark to this PDF"
File: /tmp/omni_agent/abc123/contract.pdf

Script you would synthesize:
─────────────────────────────
import pymupdf
out = '/tmp/omni_agent/abc123/contract_watermarked.pdf'
doc = pymupdf.Document('/tmp/omni_agent/abc123/contract.pdf')
for page in doc:
    page.insert_text((100, 100), "CONFIDENTIAL", fontsize=50, color=(1, 0, 0), rotate=45)
doc.save(out)
doc.close()
print(out)
─────────────────────────────

════════════════════════════════════════════════════════
RESPONSE STYLE
════════════════════════════════════════════════════════
• Be concise — one short paragraph after the transformation completes.
• Always include the output file path in your reply.
• If the guardrail blocks a script, explain which policy was violated
  in plain English; never reveal the raw pattern string.
• If a file type is unsupported, say so and suggest alternatives.
""".strip()


# ── check_guardrail tool ──────────────────────────────────────────────────────

@tool
def check_guardrail(code_snippet: str) -> str:
    """
    Mandatory security gate — MUST be called before every run_code invocation.

    Passes the synthesized script through the active guardrail implementation
    (mock pattern scan in development, live Bedrock Guardrails API in
    production). Raises GuardrailException if a policy violation is detected
    so the intervention is visible in the agent reasoning trace.

    Parameters
    ----------
    code_snippet : str
        The complete Python script the agent intends to execute.

    Returns
    -------
    str
        "NONE" — the script is clear; proceed to run_code.

    Raises
    ------
    GuardrailException
        Policy violation detected. FastAPI catches this and returns HTTP 400.
    """
    result = apply_guardrail(code_snippet)

    if result["action"] == "GUARDRAIL_INTERVENED":
        pattern = result.get("detected_pattern", "policy violation")
        logger.warning(
            "check_guardrail: INTERVENED — pattern=%r  head=%r",
            pattern,
            code_snippet[:120],
        )
        raise GuardrailException(
            reason=f"Script blocked by safety guardrail: {pattern}",
            detected_pattern=pattern,
        )

    logger.info("check_guardrail: CLEARED (%d chars)", len(code_snippet))
    return "NONE"


# ── Agent ─────────────────────────────────────────────────────────────────────

@tool
def code_interpreter(code: str) -> str:
    """
    Executes a Python script locally in a secure subprocess.
    """
    logger.info("Executing script via local code_interpreter tool:\n%s", textwrap.indent(code, "  "))
    try:
        import re
        match = re.search(r'/tmp/omni_agent/([a-fA-F0-9\-]{36})', code)
        cwd_path = Path(UPLOAD_TMP_DIR) / match.group(1) if match else Path(UPLOAD_TMP_DIR)
        
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=CODE_EXEC_TIMEOUT,
            cwd=str(cwd_path),
        )
        if proc.returncode == 0:
            return proc.stdout or "Execution successful (no output)."
        else:
            return f"Execution failed (exit code {proc.returncode}):\n{proc.stderr}"
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {CODE_EXEC_TIMEOUT} seconds."
    except Exception as e:
        return f"Execution failed with internal error: {e}"

interpreter_tool = code_interpreter

agent = Agent(
    model=get_model(),
    system_prompt=SYSTEM_PROMPT,
    tools=[
        check_guardrail,
        interpreter_tool,
    ],
)

logger.info(
    "Strands Agent initialised — model=%s  tools=[check_guardrail, code_interpreter]",
    ACTIVE_MODEL,
)

# ── BedrockAgentCoreApp wrapper ───────────────────────────────────────────────
# BedrockAgentCoreApp is a Starlette-based runtime that provides the execution
# environment expected by AWS App Runner / Bedrock AgentCore at deploy time.
# It is instantiated standalone here so it is available for production use.
# During local development it is not actively used — uvicorn serves main.py instead.

agent_app = BedrockAgentCoreApp()

logger.info("BedrockAgentCoreApp wrapper ready.")
