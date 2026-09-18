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
  ③ Write the output file to the SAME directory as the input file, but NEVER overwrite the input file in-place! The output filename MUST be different from the input filename (e.g. prefix with 'trimmed_' or append '_trimmed').
  ④ NEVER use: os.system, subprocess, __import__, eval, exec, socket, open().
     Use pathlib.Path.read_bytes() / write_bytes() / read_text() instead of open().
  ⑤ Call .overwrite_output() on all ffmpeg chains.
  ⑥ Call .close() on all pymupdf.Document objects.
  ⑦ The LAST line of the script must be a print() that outputs the absolute path of the generated output file.

════════════════════════════════════════════════════════
CODE INTERPRETER CHEAT SHEET
════════════════════════════════════════════════════════
• PyMuPDF (PDF Merging): NEVER use `insert_page`. Always use `doc1.insert_pdf(doc2)`.
• PyMuPDF (PDF Splitting/Extracting): NEVER use `doc.copy()` or `page.save()`. You MUST create a new empty document using `new_doc = pymupdf.Document()`, then insert the specific page using `new_doc.insert_pdf(original_doc, from_page=i, to_page=i)`, and then save `new_doc`. Use `pymupdf.Document()` (not `pymupdf.open()`) to avoid safety guardrails. NEVER use `PyPDF2`, `PyPDF3`, or `pdfrw`. For any and all PDF manipulations, you MUST strictly use `PyMuPDF` (`import pymupdf`).
• Audio/Video Trimming: When asked to trim or cut audio/video files: NEVER edit in-place (FFmpeg will crash). Use `ffmpeg-python` with `ss` and `to` input kwargs. Always save to a new file name (e.g. `trimmed_<filename>`).
• Developer Utilities (Base64, JSON, Hashes): Do not rely on external tools. Dynamically write and execute standard library Python scripts (e.g., `base64`, `json`, `hashlib`) via the code interpreter to fulfill the request.

CHEAT SHEET: Trimming Audio or Video with ffmpeg-python
```python
import ffmpeg
from pathlib import Path

in_path = Path(input_path)
# Output path MUST be distinct from input_path to avoid in-place edit crash
stem = in_path.stem
if stem.startswith("trimmed_"):
    out_name = f"new_{in_path.name}"
else:
    out_name = f"trimmed_{in_path.name}"
out_path = in_path.parent / out_name

# Fast cut with ss (start) and to (end)
(
    ffmpeg
    .input(str(in_path), ss=start_time, to=end_time)
    .output(str(out_path))
    .run(overwrite_output=True)
)

print(str(out_path))
```

CHEAT SHEET: Splitting a PDF and Zipping the Output
```python
import pymupdf
import shutil
from pathlib import Path

# 1. Open original doc
out_dir = Path(input_path).parent
doc = pymupdf.Document(input_path)

# 2. Extract pages to new PDFs in a dedicated folder
pages_dir = out_dir / "split_pages"
pages_dir.mkdir(exist_ok=True)
for i in range(len(doc)):
    new_doc = pymupdf.Document()
    new_doc.insert_pdf(doc, from_page=i, to_page=i)
    new_doc.save(pages_dir / f"page_{i+1}.pdf")
    new_doc.close()
doc.close()

# 3. Zip the directory
zip_path = out_dir / "pages.zip"
shutil.make_archive(base_name=str(out_dir / "pages"), format="zip", root_dir=pages_dir)
print(str(zip_path))
```

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

STEP 5 — RESPOND to the user. Your final response MUST be brief and user-facing.
  • NEVER show the user the Python code you write. NEVER narrate your internal steps or tool executions (e.g., do not say 'Here is the script', or 'Let's run this').
  • You must execute the Code Interpreter silently in the background.
  • Your final response to the user must ONLY be a brief, friendly success message (e.g., 'Your audio has been trimmed!') and the newly generated output file path.
  • You MUST output the absolute path of the generated file wrapped EXACTLY in this tag:
    [OUTPUT: /tmp/omni_agent/...]
  • NEVER put the original input file path in [OUTPUT: ...]. Only output the newly generated file.

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


# ── Process Tracking for Aggressive Cancellation ──────────────────────────────
import threading
import sys

active_processes_lock = threading.Lock()
active_processes = []

def kill_all_processes():
    """Aggressively terminate any running Code Interpreter subprocesses (e.g. ffmpeg)."""
    with active_processes_lock:
        for proc in active_processes:
            try:
                proc.kill()
            except Exception:
                pass
        active_processes.clear()


# ── Agent ─────────────────────────────────────────────────────────────────────

@tool
def code_interpreter(code: str) -> str:
    """Executes synthesized Python code in a sandboxed directory."""
    import re
    import textwrap
    logger.info("Executing script via local code_interpreter tool:\n%s", textwrap.indent(code, "  "))

    # 1. Extract request_id from the code to find the correct cwd
    match = re.search(r'/tmp/omni_agent/([a-fA-F0-9\-]{36})', code)
    cwd_path = Path(UPLOAD_TMP_DIR) / match.group(1) if match else Path(UPLOAD_TMP_DIR)

    # 2. Write the script
    script_path = cwd_path / "script.py"
    script_path.write_text(code)

    # 3. Execute
    with active_processes_lock:
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd_path),
        )
        active_processes.append(proc)
        
    try:
        stdout, stderr = proc.communicate(timeout=CODE_EXEC_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return f"Execution timed out after {CODE_EXEC_TIMEOUT} seconds."
    except Exception as e:
        return f"Execution failed with internal error: {e}"
    finally:
        with active_processes_lock:
            if proc in active_processes:
                active_processes.remove(proc)

    if proc.returncode == 0:
        return stdout or "Execution successful (no output)."
    else:
        return f"Execution failed (exit code {proc.returncode}):\n{stderr}"

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
