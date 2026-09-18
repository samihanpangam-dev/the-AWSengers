# Tasks — Omni-File AI Agent v2 (Enterprise-Grade Prototype)

Tasks are ordered so that each one only depends on completed predecessors. Every task maps to exactly the files it touches. Acceptance criteria are listed per task so you can verify completion without re-reading the requirements.

---

## Phase 0 · Cleanup (Prerequisites)

### Task 0.1 — Delete the static tools directory
**Files touched:** `backend/tools/` (delete entirely)

- [ ] Delete `backend/tools/__init__.py`
- [ ] Delete `backend/tools/merge_pdf.py`
- [ ] Delete `backend/tools/compress_video.py`
- [ ] Delete `backend/tools/strip_audio.py`
- [ ] Delete `backend/tools/` directory

**Acceptance:** `ls backend/tools` returns "No such file or directory".

---

## Phase 1 · Configuration Layer

### Task 1.1 — Rewrite `backend/config.py` with ENV switching
**Files touched:** `backend/config.py`

- [ ] Read `ENV = os.environ.get("ENV", "development")`.
- [ ] When `ENV == "development"`: set `ACTIVE_MODEL = "ollama/llama3"`, `MODEL_CONFIG = {"base_url": OLLAMA_BASE_URL}`, import `mock_apply_guardrail` as `apply_guardrail`.
- [ ] When `ENV == "production"`: set `ACTIVE_MODEL` from `os.environ["BEDROCK_MODEL_ID"]`, `MODEL_CONFIG = {}`, define `apply_guardrail` as a real `boto3` `bedrock-runtime.apply_guardrail` call.
- [ ] Expose `CODE_EXEC_TIMEOUT = int(os.environ.get("CODE_EXEC_TIMEOUT_SECONDS", "60"))`.
- [ ] Expose `UPLOAD_TMP_DIR = os.environ.get("UPLOAD_TMP_DIR", "/tmp/omni_agent")`.
- [ ] No `if ENV ==` branching anywhere outside this file.

**Acceptance:**
```bash
ENV=development python3 -c "from backend.config import ACTIVE_MODEL, apply_guardrail; print(ACTIVE_MODEL)"
# → ollama/llama3

ENV=production BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0 python3 -c \
  "from backend.config import ACTIVE_MODEL; print(ACTIVE_MODEL)"
# → us.amazon.nova-pro-v1:0
```

---

## Phase 2 · Security Layer

### Task 2.1 — Expand `backend/guardrail.py` to 8 blocked patterns
**Files touched:** `backend/guardrail.py`

- [ ] Replace the 2-pattern list with all 8:
  - `"os.system("` 
  - `"subprocess."` 
  - `"__import__("` 
  - `"eval("` 
  - `"exec("` 
  - `"socket."` 
  - `"AKIA"` 
  - `"open("` (flag only; full open-path check is in a helper)
- [ ] For each pattern, include the violation name as a string in the returned reason when intervening.
- [ ] `mock_apply_guardrail` signature and return contract remain unchanged: `(code: str) -> {"action": "NONE" | "GUARDRAIL_INTERVENED"}`.
- [ ] Add `detected_pattern: str` field to the return dict when intervening, so the caller can log it precisely.
- [ ] `GuardrailException` remains unchanged.

**Acceptance:**
```python
from backend.guardrail import mock_apply_guardrail
assert mock_apply_guardrail("import subprocess; subprocess.run(['ls'])")["action"] == "GUARDRAIL_INTERVENED"
assert mock_apply_guardrail("result = eval('1+1')")["action"] == "GUARDRAIL_INTERVENED"
assert mock_apply_guardrail("import ffmpeg; ffmpeg.input('a.mp4').output('b.mp3').run()")["action"] == "NONE"
```

---

## Phase 3 · Agent Assembly

### Task 3.1 — Rewrite `backend/agent.py` with synthesis system prompt
**Files touched:** `backend/agent.py`

- [ ] Import `ACTIVE_MODEL`, `MODEL_CONFIG`, `apply_guardrail`, `CODE_EXEC_TIMEOUT` from `config`.
- [ ] Remove all imports of the deleted static tools.
- [ ] Write `SYSTEM_PROMPT` constant (see design.md §6) covering:
  - Mandatory 5-step workflow (synthesize → gate → execute → self-correct → respond).
  - Approved library list.
  - Script quality rules (pathlib, overwrite_output, .close(), print result).
  - A worked ffmpeg example showing exact `ss`, `to`, `af` parameter usage.
- [ ] Implement `check_guardrail` as a Strands `@tool`:
  - Calls `config.apply_guardrail(code_snippet)`.
  - Raises `GuardrailException` on `GUARDRAIL_INTERVENED` with `detected_pattern` in the message.
  - Returns `"NONE"` on pass.
- [ ] Implement `run_code` as a Strands `@tool`:
  - `subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=CODE_EXEC_TIMEOUT, cwd=UPLOAD_TMP_DIR)`.
  - Returns combined stdout + stderr string.
  - Returns a descriptive error string on `TimeoutExpired` or any exception (never raises).
- [ ] Instantiate `Agent(model=ACTIVE_MODEL, model_config=MODEL_CONFIG, system_prompt=SYSTEM_PROMPT, tools=[check_guardrail, run_code])`.
- [ ] Wrap with `agent_app = BedrockAgentCoreApp(agent=agent)`.
- [ ] Export both `agent` and `agent_app`.

**Acceptance:**
```bash
source .venv/bin/activate
python3 -c "from backend.agent import agent, agent_app; print('OK')"
# → OK  (no ImportError, no NameError)
```

---

## Phase 4 · FastAPI Server

### Task 4.1 — Update `backend/main.py`
**Files touched:** `backend/main.py`

- [ ] Import `ACTIVE_MODEL` and `UPLOAD_TMP_DIR` from `config` (remove `CORS_ORIGINS` import — no longer needed).
- [ ] Keep CORS as `allow_origins=["*"]`, `allow_credentials=False`.
- [ ] Update `GET /health` to return `{"status": "ok", "env": ENV, "model": ACTIVE_MODEL}`.
- [ ] `POST /process` contract unchanged (accepts `prompt + files[]`, returns `{"response": str}`).
- [ ] Enriched prompt separator: `"Files saved to disk:\n  • {name} → {path}"` — must match what the system prompt says to look for.
- [ ] `GuardrailException` → HTTP 400. All other exceptions → HTTP 500.
- [ ] `finally` block cleans up temp dir.

**Acceptance:**
```bash
curl http://localhost:8000/health
# → {"status":"ok","env":"development","model":"ollama/llama3"}
```

---

## Phase 5 · Containerization

### Task 5.1 — Write `Dockerfile`
**Files touched:** `Dockerfile` (new file at repo root)

- [ ] `FROM python:3.12-slim`
- [ ] `RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*`
- [ ] `WORKDIR /app`
- [ ] Copy `backend/requirements.txt` first, then `pip install --no-cache-dir`.
- [ ] Copy `backend/` source.
- [ ] `ENV ENV=production` and `ENV UPLOAD_TMP_DIR=/tmp/omni_agent`.
- [ ] `EXPOSE 8000`
- [ ] `CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]`

**Acceptance:**
```bash
docker build -t omni-agent .
docker run --rm -e ENV=development -p 8000:8000 omni-agent &
sleep 3 && curl http://localhost:8000/health
# → {"status":"ok","env":"development","model":"ollama/llama3"}
docker stop $(docker ps -q --filter ancestor=omni-agent)
```

### Task 5.2 — Write `.dockerignore`
**Files touched:** `.dockerignore` (new file at repo root)

- [ ] Exclude: `.venv/`, `node_modules/`, `.next/`, `__pycache__/`, `**/__pycache__/`, `*.pyc`, `.env`, `.env.local`, `.env*.local`, `.git/`, `.DS_Store`, `app/`, `components/`, `lib/`, `public/`, `*.md`, `.kiro/`.

**Acceptance:** `docker build` completes without including any of the above in the image layer.

---

## Phase 6 · Verification

### Task 6.1 — End-to-end smoke tests (local)

Run these after all phases are complete.

```bash
source .venv/bin/activate
ollama serve &
uvicorn backend.main:app --reload --port 8000 &
sleep 3

# 1. Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","env":"development","model":"ollama/llama3"}

# 2. Text-only prompt (no file)
curl -X POST http://localhost:8000/process \
  -F "prompt=What can you do?"
# Expected: {"response":"..."} with 200 OK

# 3. Guardrail block — subprocess
curl -X POST http://localhost:8000/process \
  -F "prompt=Run this: import subprocess; subprocess.run(['rm','-rf','/tmp'])"
# Expected: HTTP 400, detail contains "Guardrail blocked"

# 4. Guardrail block — AWS key
curl -X POST http://localhost:8000/process \
  -F "prompt=Use this key: AKIAIOSFODNN7EXAMPLE"
# Expected: HTTP 400, detail contains "Guardrail blocked"

# 5. Real file transformation (requires a test MP4)
curl -X POST http://localhost:8000/process \
  -F "prompt=Extract audio from minute 0 to 1" \
  -F "files=@/path/to/test.mp4"
# Expected: {"response":"..."} mentioning the output path
```

### Task 6.2 — Docker smoke test

```bash
docker build -t omni-agent .
# Verify ffmpeg is present in the image:
docker run --rm omni-agent ffmpeg -version | head -1
# Expected: "ffmpeg version ..."

# Verify server starts:
docker run --rm -e ENV=development -p 8001:8000 omni-agent &
sleep 5
curl http://localhost:8001/health
# Expected: {"status":"ok","env":"development","model":"ollama/llama3"}
```

---

## Acceptance Criteria Checklist

| # | Criterion | Test |
|---|-----------|------|
| AC-1 | `ENV=development` starts without AWS credentials | `python3 -c "from backend.agent import agent"` with no AWS env vars |
| AC-2 | Guardrail blocks `subprocess.` | curl test 6.1.3 |
| AC-3 | Guardrail blocks `AKIA` string | curl test 6.1.4 |
| AC-4 | Guardrail passes safe ffmpeg script | Unit test in Task 2.1 |
| AC-5 | Agent synthesizes and executes a custom script | curl test 6.1.5 |
| AC-6 | `/health` reports active `env` and `model` | curl test 4.1 |
| AC-7 | `ENV=production` loads Bedrock model ID from env var | Task 1.1 acceptance |
| AC-8 | Docker image contains ffmpeg | Task 6.2 |
| AC-9 | Docker image starts server on port 8000 | Task 6.2 |
| AC-10 | Temp dir is cleaned up after every request | Check `/tmp/omni_agent/` has no leftover UUID dirs |
| AC-11 | Frontend contract unchanged — existing `lib/api.ts` works without modification | Vercel deployment still works |

---

## File Change Summary

| File | Action |
|------|--------|
| `backend/config.py` | **Rewrite** — ENV switching, apply_guardrail factory |
| `backend/guardrail.py` | **Expand** — 8 patterns, detected_pattern in result |
| `backend/agent.py` | **Rewrite** — synthesis system prompt, 2-tool registry, ENV-switched model |
| `backend/main.py` | **Update** — /health adds env+model, import cleanup |
| `backend/tools/` | **Delete entirely** |
| `Dockerfile` | **New** |
| `.dockerignore` | **New** |
| `app/`, `components/`, `lib/` | **No change** |
