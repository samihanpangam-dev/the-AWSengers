# Requirements — Omni-File AI Agent v2 (Enterprise-Grade Prototype)

## 1. Overview

Version 2 replaces the static tool-dispatch architecture with a **dynamic synthesis pipeline**: the Strands Agent writes custom Python scripts at runtime, gates every script through a mandatory security layer, and executes it inside a sandboxed code interpreter. A single `ENV` environment variable switches the entire stack between local development (Ollama + mock guardrails + subprocess sandbox) and production (Amazon Bedrock Claude + live Guardrails API + BedrockAgentCore CodeInterpreter) without touching any business logic.

---

## 2. Functional Requirements

### FR-1 · Dynamic Code Synthesis (Core Capability)
- **FR-1.1** The Strands Agent MUST synthesize a custom Python script in response to any file-transformation prompt it receives, rather than routing to a pre-written wrapper function.
- **FR-1.2** Synthesized scripts MUST be complete, runnable Python programs that import whatever libraries are needed (e.g., `ffmpeg-python`, `PyMuPDF`, `Pillow`, `pydub`) to satisfy the request.
- **FR-1.3** Example: a prompt of *"extract audio from minute 1 to 3 and amplify by 15%"* MUST cause the agent to synthesize a script that uses `ffmpeg-python` with the exact trim (`ss=60`, `to=180`) and audio filter (`volume=1.15`) parameters, then execute it against the uploaded file.
- **FR-1.4** Example: a prompt of *"merge these two PDFs and add a watermark"* MUST cause the agent to synthesize a PyMuPDF script that performs both operations, not invoke a static `merge_pdf` tool.
- **FR-1.5** The agent MUST include the uploaded file's on-disk path in every synthesized script so the script operates on the correct file.
- **FR-1.6** The agent MUST return the output file path or a summary of results to the user after successful execution.

### FR-2 · Security Layer (Mock Bedrock Guardrails)
- **FR-2.1** A function `mock_apply_guardrail(code_snippet: str) -> dict` MUST be called on every synthesized script before execution. No exceptions.
- **FR-2.2** The following patterns MUST trigger `{"action": "GUARDRAIL_INTERVENED"}` and block execution:
  - `os.system(` — arbitrary shell execution
  - `subprocess.` — subprocess spawning
  - `__import__(` — dynamic import bypass
  - `eval(` — code injection via eval
  - `exec(` — code injection via exec
  - `open(` when combined with write mode (`"w"`, `"wb"`, `"a"`) outside the designated temp directory
  - `AKIA` — AWS IAM access key prefix (secret leak detection)
  - `socket.` — raw network access
- **FR-2.3** If none of the above patterns are present, the function MUST return `{"action": "NONE"}` and allow execution.
- **FR-2.4** When the guardrail intervenes, the agent MUST return a human-readable safety warning to the user explaining which policy was violated. It MUST NOT execute the script or any part of it.
- **FR-2.5** The guardrail check MUST be enforced by the `check_guardrail` Strands `@tool` so the call is visible in the agent's reasoning trace and cannot be bypassed by the LLM.
- **FR-2.6** In `ENV=production`, `mock_apply_guardrail` MUST be replaced by a real call to the AWS Bedrock Guardrails API (`bedrock-runtime.apply_guardrail`) using the guardrail ID stored in `BEDROCK_GUARDRAIL_ID`.

### FR-3 · Code Interpreter (Sandboxed Execution)
- **FR-3.1** In `ENV=development` (default), synthesized scripts MUST be executed in an isolated subprocess via `run_code(code: str) -> str` using `subprocess.run([sys.executable, "-c", code], timeout=60)`.
- **FR-3.2** The subprocess MUST be given a working directory of the request's temp folder so relative file paths resolve correctly.
- **FR-3.3** Combined stdout + stderr MUST be captured and returned to the agent as the tool result.
- **FR-3.4** Execution MUST time out after 60 seconds and return an error string rather than hanging.
- **FR-3.5** In `ENV=production`, `run_code` MUST delegate to `bedrock_agentcore.tools.CodeInterpreter`, uploading the input file into the sandbox session before execution and downloading the output file after.

### FR-4 · FastAPI Server
- **FR-4.1** A single FastAPI application in `backend/main.py` MUST expose:
  - `GET /health` — returns `{"status": "ok", "env": "<ENV value>", "model": "<active model ID>"}`.
  - `POST /process` — accepts `multipart/form-data` with `prompt: str` and `files: list[UploadFile]`.
- **FR-4.2** `POST /process` MUST return `{"response": str}` on success.
- **FR-4.3** `POST /process` MUST return HTTP 400 with `{"detail": "Guardrail blocked: <reason>"}` when the guardrail intervenes.
- **FR-4.4** `POST /process` MUST return HTTP 500 with `{"detail": "Agent error: <message>"}` on unexpected failures.
- **FR-4.5** CORS MUST be configured with `allow_origins=["*"]` and `allow_credentials=False` to support Vercel + Cloudflare tunnel deployments.
- **FR-4.6** Each request MUST save uploaded files to an isolated UUID-scoped temp directory under `UPLOAD_TMP_DIR` and clean it up in a `finally` block.

### FR-5 · Environment-Switched Configuration
- **FR-5.1** A `backend/config.py` module MUST read `os.environ.get("ENV", "development")` and expose a single `settings` object (or module-level constants) that the rest of the codebase imports.
- **FR-5.2** When `ENV=development`:
  - LLM provider: Ollama (`ollama/llama3`) at `OLLAMA_BASE_URL`
  - Guardrail: `mock_apply_guardrail` from `guardrail.py`
  - Code execution: local subprocess `run_code`
- **FR-5.3** When `ENV=production`:
  - LLM provider: Amazon Bedrock (`us.amazon.nova-pro-v1:0` or value of `BEDROCK_MODEL_ID`)
  - Guardrail: live Bedrock Guardrails API using `BEDROCK_GUARDRAIL_ID` + `BEDROCK_GUARDRAIL_VERSION`
  - Code execution: `bedrock_agentcore.tools.CodeInterpreter` in AWS region `AWS_REGION`
- **FR-5.4** No `if ENV == ...` branching MUST exist outside `config.py` and `agent.py`. All other modules import from `config` and remain environment-agnostic.

### FR-6 · Containerization (Dockerfile)
- **FR-6.1** A `Dockerfile` at the repository root MUST build a self-contained image that runs the FastAPI server.
- **FR-6.2** Base image MUST be `python:3.12-slim`.
- **FR-6.3** `RUN apt-get install -y ffmpeg` MUST be included so media-processing tools are available inside the container.
- **FR-6.4** `backend/requirements.txt` MUST be installed via `pip install --no-cache-dir`.
- **FR-6.5** The container MUST start uvicorn on `0.0.0.0:8000` via `CMD`.
- **FR-6.6** A `.dockerignore` file MUST exclude `.venv`, `node_modules`, `.next`, `__pycache__`, and `.env*` files.
- **FR-6.7** The `ENV` environment variable MUST be injectable at `docker run` time via `-e ENV=production`.

### FR-7 · Frontend Integration (No Change Required)
- **FR-7.1** The existing React frontend, `lib/api.ts`, and `components/chat-panel.tsx` require no changes — the backend contract (`POST /process`, `GET /health`, JSON shapes) is preserved.
- **FR-7.2** `NEXT_PUBLIC_API_URL` environment variable in Vercel continues to point at the Cloudflare tunnel or production URL.

---

## 3. Non-Functional Requirements

### NFR-1 · Dynamic Synthesis Quality
- **NFR-1.1** The agent's system prompt MUST provide enough context (file paths, library names, parameter conventions) that the LLM generates syntactically correct Python on the first attempt for common transformations.
- **NFR-1.2** If the generated script fails at runtime, the agent MUST catch the error output, attempt to self-correct the script once, and re-submit through the guardrail before reporting failure to the user.

### NFR-2 · Security
- **NFR-2.1** The guardrail is the ONLY gate between the LLM's output and execution. It MUST be impossible for the agent to call `run_code` without first calling `check_guardrail` — enforced by the system prompt and tool description.
- **NFR-2.2** Temp directories MUST be UUID-scoped and deleted after every request regardless of success or failure.
- **NFR-2.3** Synthesized scripts MUST only be allowed to write files under the request's temp directory.

### NFR-3 · Performance
- **NFR-3.1** The code execution timeout MUST be 60 seconds in development, configurable via `CODE_EXEC_TIMEOUT_SECONDS` env var.
- **NFR-3.2** The FastAPI server MUST handle requests concurrently using `async` endpoints and `await upload.read()`.

### NFR-4 · Observability
- **NFR-4.1** Every request MUST log: request ID, prompt (first 120 chars), file count, tool selected, guardrail result, and execution outcome at INFO level.
- **NFR-4.2** Guardrail interventions MUST be logged at WARNING level with the blocked pattern name.
- **NFR-4.3** The `GET /health` endpoint MUST expose the active `ENV` and model ID so operators can confirm which mode is running.

### NFR-5 · Maintainability
- **NFR-5.1** `config.py` is the single file that must be changed when adding a new environment or model.
- **NFR-5.2** `guardrail.py` is the single file that must be changed to swap mock → real Bedrock Guardrails.
- **NFR-5.3** `agent.py` is the single file that must be changed to register new tools or adjust the system prompt.

---

## 4. Constraints & Assumptions

| # | Constraint / Assumption |
|---|-------------------------|
| C-1 | `ENV=development` is the default; the server starts locally without any AWS credentials. |
| C-2 | Ollama must be running at `http://localhost:11434` with `llama3` pulled for local mode. |
| C-3 | `ffmpeg` binary must be on PATH in development; it is baked into the Docker image for production. |
| C-4 | Python 3.12 is the target runtime (matches the Dockerfile base image). |
| C-5 | The three legacy fast-path tools (`merge_pdf`, `compress_video`, `strip_audio`) are REMOVED. The agent synthesizes equivalent scripts dynamically. |
| C-6 | `ENV=production` requires `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`, `BEDROCK_GUARDRAIL_VERSION` to be set. |
| C-7 | The frontend contract (endpoint URLs, JSON field names) does not change between v1 and v2. |
