# Design — Omni-File AI Agent v2 (Enterprise-Grade Prototype)

---

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Browser  (Next.js 16 / React 19, deployed on Vercel)                        │
│                                                                              │
│   FileUploadSidebar          ChatPanel                                       │
│   • drag & drop              • message history                               │
│   • rawFiles: File[]         • real fetch() via lib/api.ts                   │
│         │                          │                                         │
│         └──────────┬───────────────┘                                         │
│                    │  POST /process  multipart/form-data                     │
│                    │  { prompt, files[] }                                    │
└────────────────────┼────────────────────────────────────────────────────────┘
                     │  NEXT_PUBLIC_API_URL (Cloudflare tunnel or prod URL)
                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  FastAPI  (uvicorn, port 8000)                                               │
│  CORS allow_origins=["*"]  allow_credentials=False                          │
│                                                                              │
│  POST /process                                                               │
│    1. save uploads → /tmp/omni_agent/<uuid>/                                 │
│    2. build enriched prompt (file paths injected)                            │
│    3. agent(enriched_prompt)                                                 │
│    4. cleanup temp dir                                                       │
│    5. return {"response": str}                                               │
│                                                                              │
│  GET /health → {"status":"ok","env":"...","model":"..."}                     │
└────────────────────┬────────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  config.py  ──  ENV=development (default) / ENV=production                  │
│                                                                              │
│  ┌─────────────────────────┐    ┌──────────────────────────────────────────┐ │
│  │   ENV=development        │    │   ENV=production                         │ │
│  │   model: ollama/llama3   │    │   model: BEDROCK_MODEL_ID                │ │
│  │   guardrail: mock        │    │   guardrail: Bedrock Guardrails API      │ │
│  │   executor: subprocess   │    │   executor: CodeInterpreter (AWS)        │ │
│  └─────────────────────────┘    └──────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Strands Agent                                                               │
│  system_prompt: dynamic synthesis policy (see §3)                           │
│                                                                              │
│  Tools:                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐ │
│  │ check_guardrail │  │    run_code      │  │  (prod) bedrock_run_code     │ │
│  │ @tool           │  │  @tool           │  │  @tool  via CodeInterpreter  │ │
│  │ always first    │  │  subprocess      │  │                              │ │
│  └─────────────────┘  └─────────────────┘  └──────────────────────────────┘ │
│                                                                              │
│  BedrockAgentCoreApp wrapper (pass-through locally, active in prod)         │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Layout

```
the AWSengers/
├── backend/
│   ├── __init__.py
│   ├── config.py          ← ENV switch; single source of truth for all settings
│   ├── guardrail.py       ← mock_apply_guardrail() + GuardrailException
│   ├── agent.py           ← Strands Agent, system prompt, check_guardrail @tool,
│   │                         run_code @tool, BedrockAgentCoreApp wrapper
│   ├── main.py            ← FastAPI app, CORS, /health, /process
│   └── requirements.txt
├── Dockerfile
├── .dockerignore
├── app/                   ← Next.js (unchanged)
├── components/            ← React (unchanged)
├── lib/
│   ├── api.ts             ← fetch() client (unchanged)
│   └── ...
└── .kiro/specs/omni-file-agent-v2/
    ├── requirements.md
    ├── design.md          ← this file
    └── tasks.md
```

> **What was removed vs v1:**
> `backend/tools/` directory and all three static tools (`merge_pdf`, `compress_video`, `strip_audio`) are deleted. The agent synthesizes equivalent scripts dynamically via `run_code`.

---

## 3. Dynamic Synthesis Pipeline

This is the critical architectural change from v1. Instead of the LLM selecting from a fixed menu of tools, it writes the full transformation script itself.

```
User prompt: "extract audio from minute 1 to 3 and amplify by 15%"
Uploaded file: /tmp/omni_agent/<uuid>/interview.mp4
                │
                ▼
┌──────────────────────────────────────────────────┐
│  Strands Agent  (LLM reasoning loop)             │
│                                                  │
│  Step 1 — SYNTHESIZE                             │
│  LLM reads system prompt + enriched prompt and   │
│  writes a complete Python script:                │
│                                                  │
│    import ffmpeg                                 │
│    (                                             │
│      ffmpeg                                      │
│        .input('/tmp/.../interview.mp4',          │
│                ss=60, to=180)                    │
│        .output('/tmp/.../out.mp3',               │
│                af='volume=1.15',                 │
│                acodec='libmp3lame')              │
│        .overwrite_output()                       │
│        .run(quiet=True)                          │
│    )                                             │
│    print('/tmp/.../out.mp3')                     │
│                                                  │
│  Step 2 — GATE  (mandatory, cannot be skipped)   │
│  agent calls: check_guardrail(script)            │
│    → mock_apply_guardrail scans for 8 patterns   │
│    → returns NONE  ──► proceed                   │
│    → returns GUARDRAIL_INTERVENED ──► STOP       │
│                                                  │
│  Step 3 — EXECUTE                                │
│  agent calls: run_code(script)                   │
│    → subprocess.run([python, "-c", script],      │
│        cwd=tmp_dir, timeout=60)                  │
│    → captures stdout + stderr                    │
│    → returns output string to agent              │
│                                                  │
│  Step 4 — RESPOND                                │
│  LLM reads execution output and composes a       │
│  natural-language reply to the user.             │
│  "Done — extracted 2 min audio and amplified     │
│   by 15%. File saved to out.mp3."                │
└──────────────────────────────────────────────────┘
```

### Self-correction loop (NFR-1.2)

```
run_code returns stderr / non-zero exit
          │
          ▼
   LLM sees error in tool result
          │
          ▼
   LLM revises script (attempt 2)
          │
          ▼
   check_guardrail (mandatory again)
          │
          ▼
   run_code (attempt 2)
          │
    ┌─────┴──────┐
  success      still failing
    │               │
  respond       report error to user
```

---

## 4. Guardrail Design

### 4.1 Pattern Table

| Pattern | Threat modelled | Intervention message |
|---------|----------------|---------------------|
| `os.system(` | Arbitrary shell execution | "Dangerous shell execution detected" |
| `subprocess.` | Subprocess spawning | "Subprocess spawning is not permitted" |
| `__import__(` | Dynamic import bypass | "Dynamic import bypass detected" |
| `eval(` | Code injection via eval | "eval() usage is not permitted" |
| `exec(` | Code injection via exec | "exec() usage is not permitted" |
| `socket.` | Raw network access | "Raw network access is not permitted" |
| `AKIA` | AWS credential leak | "Potential AWS credential detected" |
| `"w"` / `"wb"` / `"a"` + `open(` outside tmp | Filesystem write escape | "Unauthorised file write path" |

### 4.2 Development vs Production Guardrail

```python
# config.py governs which implementation is used:

if ENV == "development":
    def apply_guardrail(code: str) -> dict:
        return mock_apply_guardrail(code)          # local pattern scan

elif ENV == "production":
    def apply_guardrail(code: str) -> dict:
        return bedrock_client.apply_guardrail(     # real AWS API
            guardrailIdentifier=BEDROCK_GUARDRAIL_ID,
            guardrailVersion=BEDROCK_GUARDRAIL_VERSION,
            source="INPUT",
            content=[{"text": {"text": code}}],
        )
```

### 4.3 Guardrail Enforcement Flow

```
agent writes script
      │
      ▼
check_guardrail(@tool) called by LLM
      │
      ▼
config.apply_guardrail(script)
      │
   ┌──┴──────────────────────────┐
   │ NONE                        │ GUARDRAIL_INTERVENED
   │                             │
   ▼                             ▼
run_code(@tool)          raise GuardrailException(reason)
   │                             │
   ▼                             ▼
execution result          FastAPI catches →
returned to LLM           HTTP 400 {"detail": "Guardrail blocked: ..."}
                                  │
                                  ▼
                          ChatPanel shows amber error bubble
```

---

## 5. Environment-Switching Design

`config.py` is the ONLY file that reads environment variables and makes branching decisions. Every other module imports from it.

```python
# backend/config.py  (abridged design)

import os
import boto3

ENV = os.environ.get("ENV", "development")

# ── Model ──────────────────────────────────────────────────────────────────
if ENV == "production":
    ACTIVE_MODEL      = os.environ["BEDROCK_MODEL_ID"]   # e.g. us.amazon.nova-pro-v1:0
    MODEL_CONFIG      = {}                               # boto3 handles region via AWS_REGION
else:
    ACTIVE_MODEL      = "ollama/llama3"
    MODEL_CONFIG      = {"base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")}

# ── Guardrail ──────────────────────────────────────────────────────────────
if ENV == "production":
    _bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    def apply_guardrail(code: str) -> dict:
        resp = _bedrock.apply_guardrail(
            guardrailIdentifier=os.environ["BEDROCK_GUARDRAIL_ID"],
            guardrailVersion=os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT"),
            source="INPUT",
            content=[{"text": {"text": code}}],
        )
        action = "GUARDRAIL_INTERVENED" if resp["action"] == "GUARDRAIL_INTERVENED" else "NONE"
        return {"action": action}
else:
    from .guardrail import mock_apply_guardrail as apply_guardrail

# ── Code executor ──────────────────────────────────────────────────────────
CODE_EXEC_TIMEOUT = int(os.environ.get("CODE_EXEC_TIMEOUT_SECONDS", "60"))

# ── Misc ──────────────────────────────────────────────────────────────────
UPLOAD_TMP_DIR = os.environ.get("UPLOAD_TMP_DIR", "/tmp/omni_agent")
```

### Environment variable reference

| Variable | Required in | Default | Purpose |
|----------|-------------|---------|---------|
| `ENV` | both | `development` | Master switch |
| `OLLAMA_BASE_URL` | dev | `http://localhost:11434` | Ollama endpoint |
| `BEDROCK_MODEL_ID` | prod | — | Bedrock model ARN / ID |
| `BEDROCK_GUARDRAIL_ID` | prod | — | Bedrock Guardrail identifier |
| `BEDROCK_GUARDRAIL_VERSION` | prod | `DRAFT` | Guardrail version |
| `AWS_REGION` | prod | `us-east-1` | boto3 region |
| `AWS_ACCESS_KEY_ID` | prod | — | IAM credential |
| `AWS_SECRET_ACCESS_KEY` | prod | — | IAM credential |
| `CODE_EXEC_TIMEOUT_SECONDS` | both | `60` | Subprocess timeout |
| `UPLOAD_TMP_DIR` | both | `/tmp/omni_agent` | Temp file root |

---

## 6. System Prompt Design

The system prompt is the engine of dynamic synthesis. It must be precise enough that even a mid-tier local model (llama3) produces runnable scripts.

```
SYSTEM PROMPT (stored in agent.py as SYSTEM_PROMPT constant)
─────────────────────────────────────────────────────────────

You are the Omni-File AI Agent. You transform files by synthesizing and
executing custom Python scripts. You have two tools: check_guardrail and
run_code.

## Mandatory workflow — follow this EVERY time:

1. READ the user's request and identify the input file path(s) from the
   enriched prompt (they are listed after "Files saved to disk:").

2. WRITE a complete, self-contained Python script that:
   - Uses only these approved libraries: ffmpeg-python, PyMuPDF (fitz),
     Pillow, pydub, json, pathlib, shutil, re, math, datetime, csv.
   - Reads from the exact input file path(s) provided.
   - Writes output to the same directory as the input file.
   - Ends with a print() statement that outputs the output file path
     or a plain-English summary of the result.
   - NEVER uses: os.system, subprocess, __import__, eval, exec, socket.

3. CALL check_guardrail(script) with the full script string.
   - If it returns "NONE", proceed to step 4.
   - If it raises an error, STOP and tell the user why.

4. CALL run_code(script) with the same script string.
   - Read the output carefully.
   - If there is an error in the output, fix the script and repeat
     from step 3. You may attempt self-correction once.

5. RESPOND to the user with:
   - What transformation was applied.
   - The output file path or result.
   - Any important caveats (e.g., lossy compression, page count).

## Script quality rules:
- Always use pathlib.Path for file operations, not os.path.
- Always call .overwrite_output() on ffmpeg chains.
- Always close PyMuPDF document objects with .close().
- Always print() the result path as the last line.

## Example — audio extraction with amplification:
User: "extract audio from minute 1 to 3 and amplify by 15%"
File: /tmp/omni_agent/abc123/interview.mp4

Script you would write:
  import ffmpeg
  out = '/tmp/omni_agent/abc123/interview_clip.mp3'
  (ffmpeg
    .input('/tmp/omni_agent/abc123/interview.mp4', ss=60, to=180)
    .output(out, af='volume=1.15', acodec='libmp3lame', audio_bitrate='192k')
    .overwrite_output()
    .run(quiet=True))
  print(out)
```

---

## 7. FastAPI Request Lifecycle

```
POST /process
  │
  ├─ 1. Create /tmp/omni_agent/<uuid4>/
  ├─ 2. Write each UploadFile to disk
  ├─ 3. Build enriched_prompt:
  │       "{user_prompt}\n\nFiles saved to disk:\n  • {name} → {path}\n..."
  ├─ 4. agent(enriched_prompt)
  │       └─ Strands reasoning loop (see §3)
  │           ├─ check_guardrail(@tool)
  │           │     └─ config.apply_guardrail(code)
  │           └─ run_code(@tool)
  │                 └─ subprocess.run(...)  OR  CodeInterpreter
  ├─ 5. return {"response": str(result)}
  │
  ├─ GuardrailException  →  HTTP 400  {"detail": "Guardrail blocked: ..."}
  └─ Exception           →  HTTP 500  {"detail": "Agent error: ..."}
  └─ finally: shutil.rmtree(tmp_dir)
```

---

## 8. Dockerfile Design

```dockerfile
# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim

# System dependencies — ffmpeg is required for all media operations.
# Installed at build time so the container is self-contained.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source so Docker layer cache is
# preserved on source-only changes.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application source
COPY backend/ ./backend/

# Runtime configuration
ENV ENV=production
ENV UPLOAD_TMP_DIR=/tmp/omni_agent
EXPOSE 8000

# Uvicorn in single-worker mode. Increase --workers for production load.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### .dockerignore contents

```
.venv/
node_modules/
.next/
__pycache__/
**/__pycache__/
*.pyc
.env
.env.local
.env*.local
.git/
.DS_Store
app/
components/
lib/
public/
*.md
```

---

## 9. What Changes from v1 → v2

| Component | v1 | v2 |
|-----------|----|----|
| `backend/tools/` | 3 static tools (merge_pdf, compress_video, strip_audio) | **Deleted** |
| `agent.py` tools | merge_pdf, compress_video, strip_audio, check_guardrail, run_code | check_guardrail, run_code only |
| Guardrail patterns | 2 (AKIA, prompt injection) | **8** (adds os.system, subprocess, eval, exec, socket, __import__) |
| Config | Hardcoded constants | **ENV-switched** settings object |
| Agent behaviour | Route to fixed tool | **Synthesize** custom script every time |
| System prompt | Short routing policy | **Full synthesis guide** with examples and quality rules |
| Deployment | Local only | **Dockerfile** + App Runner readiness |
| `/health` response | `{"status":"ok"}` | `{"status":"ok","env":"...","model":"..."}` |

---

## 10. Key Design Decisions & Rationale

**Why remove the static tools?**
Static tools hard-code transformation parameters. A user who wants "compress video to 720p with CRF 24 and keep only the centre crop" cannot express that through a `compress_video(input, output)` signature. Dynamic synthesis handles arbitrary parameterization without code changes.

**Why keep check_guardrail as a Strands @tool rather than a middleware?**
Registering it as a tool makes it appear in the agent's reasoning trace. If the agent tries to skip it, the omission is visible in logs. A middleware would be invisible and harder to audit.

**Why subprocess for local code execution instead of exec()?**
`exec()` runs in the same process memory — a buggy script can corrupt server state. `subprocess.run` isolates the script in a child process. The guardrail blocks `exec(` in synthesized scripts for the same reason.

**Why python:3.12-slim and not python:3.12-alpine?**
`ffmpeg-python` and `PyMuPDF` both have native C extensions. Alpine uses musl libc which causes build failures with some wheels. Debian slim avoids this entirely.

**Why ENV=production is set in the Dockerfile CMD layer but injectable at runtime?**
The Dockerfile default makes it harder to accidentally run in dev mode in a production container. Teams can still override with `docker run -e ENV=development` for local container testing.
