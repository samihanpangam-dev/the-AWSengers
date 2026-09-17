# Requirements — Omni-File AI Agent

## 1. Overview

The Omni-File AI Agent is a full-stack application that allows users to upload arbitrary files (PDFs, videos, audio, images) and interact with them through a conversational AI interface. The agent intelligently routes requests to specialised fast-path tools or a dynamic code interpreter, and all generated code passes through a guardrail layer before execution.

---

## 2. Functional Requirements

### FR-1 · File Upload
- **FR-1.1** Users must be able to upload one or more files via drag-and-drop or file-browser in the sidebar.
- **FR-1.2** Supported file types: `.pdf`, `.mp4`, `.mp3`, `.jpg`, `.jpeg`, `.png`, `.wav`, `.mov`, `.webm`.
- **FR-1.3** Each uploaded file must be transmitted to the backend as part of a `multipart/form-data` POST request.
- **FR-1.4** The sidebar must display each file's name, size, type icon, and a remove button.

### FR-2 · Chat Interface
- **FR-2.1** Users must be able to type a natural-language prompt describing the desired file transformation or query.
- **FR-2.2** The chat panel must show a loading/processing state while the backend is working.
- **FR-2.3** The agent's textual response must be displayed in the chat after processing.
- **FR-2.4** Chat history must persist for the duration of the browser session.

### FR-3 · Backend Agent
- **FR-3.1** The backend must expose a single HTTP endpoint `POST /process` that accepts `multipart/form-data` with fields `prompt` (string) and `files[]` (one or more uploaded files).
- **FR-3.2** The endpoint must return a JSON response `{ "response": string }`.
- **FR-3.3** A Strands `Agent` must orchestrate tool selection and execution, using a local Ollama model (`ollama/llama3`) as the LLM provider.
- **FR-3.4** The agent must be wrapped by a `BedrockAgentCoreApp` for deployment compatibility.

### FR-4 · Dedicated Fast-Path Tools
- **FR-4.1 merge_pdf** — accepts a list of PDF file paths and merges them into a single output PDF using PyMuPDF (`fitz`). Returns the output file path.
- **FR-4.2 compress_video** — accepts an MP4 input path and an output path, compresses the video using `ffmpeg-python` (CRF 28, `libx264`). Returns the output file path.
- **FR-4.3 strip_audio** — accepts an MP4 input path and an output path, extracts the audio track as MP3 using `ffmpeg-python`. Returns the output file path.

### FR-5 · Mock Guardrail System
- **FR-5.1** A function `mock_apply_guardrail(code_snippet: str)` must be called on any code before the agent executes it.
- **FR-5.2** If the snippet contains the string `"AKIA"` (simulating an AWS secret key), the function must return `{"action": "GUARDRAIL_INTERVENED"}` and block execution.
- **FR-5.3** If the snippet contains the string `"ignore all previous instructions"` (simulating prompt injection), the function must return `{"action": "GUARDRAIL_INTERVENED"}` and block execution.
- **FR-5.4** If neither pattern is detected, the function must return `{"action": "NONE"}` and allow execution to proceed.
- **FR-5.5** The agent's system prompt must instruct it to route all dynamically-generated code through the guardrail before execution.

### FR-6 · Code Interpreter Fallback
- **FR-6.1** `AgentCoreCodeInterpreter` from `bedrock_agentcore` must be attached to the Strands agent as a tool.
- **FR-6.2** The agent's system prompt must instruct it to fall back to the code interpreter for any file transformation not covered by the three dedicated tools.
- **FR-6.3** The code interpreter must write and execute a custom Python script dynamically at runtime.

### FR-7 · CORS & Frontend Integration
- **FR-7.1** The FastAPI application must permit cross-origin requests from `http://localhost:3000` and `http://localhost:3001` (v0.dev dev server ports).
- **FR-7.2** Allowed HTTP methods: `GET`, `POST`, `OPTIONS`.
- **FR-7.3** The frontend must provide a `fetch()` call that sends `multipart/form-data` (files + prompt) to `POST http://localhost:8000/process`.

---

## 3. Non-Functional Requirements

### NFR-1 · Performance
- **NFR-1.1** Fast-path tools (merge_pdf, compress_video, strip_audio) must complete without LLM round-trips; the agent should invoke them directly via tool selection.
- **NFR-1.2** The Ollama local model is used specifically to avoid cloud-API latency during development.

### NFR-2 · Security
- **NFR-2.1** The guardrail must be the first gate before any dynamic code execution; a `GUARDRAIL_INTERVENED` result must short-circuit the pipeline and return a safe error message to the user.
- **NFR-2.2** Uploaded files must be stored in a temporary directory scoped to the request and cleaned up after processing.

### NFR-3 · Reliability
- **NFR-3.1** If a dedicated tool raises an exception, the agent must catch it, log the error, and fall back to the code interpreter.
- **NFR-3.2** If the code interpreter also fails, the agent must return a descriptive error message to the user rather than crashing.

### NFR-4 · Maintainability
- **NFR-4.1** Each tool must live in its own file under `backend/tools/`.
- **NFR-4.2** The guardrail must live in its own file `backend/guardrail.py` so it can be swapped for a real Bedrock Guardrails call without touching other modules.
- **NFR-4.3** Configuration (model ID, CORS origins, temp dir) must be centralised in `backend/config.py`.

### NFR-5 · Observability
- **NFR-5.1** The backend must log each request (files received, tool selected, guardrail result) to stdout at INFO level.

---

## 4. Constraints & Assumptions

| # | Constraint / Assumption |
|---|-------------------------|
| C-1 | Ollama must be running locally on `http://localhost:11434` with the `llama3` model pulled. |
| C-2 | `ffmpeg` binary must be available on the system PATH. |
| C-3 | Python ≥ 3.11 is required. |
| C-4 | The frontend is a Next.js 16 / React 19 app using Tailwind CSS and shadcn components. |
| C-5 | `strands-agents` and `bedrock-agentcore` are pip-installable packages. |
| C-6 | The mock guardrail is a demo substitute; production would call the real AWS Bedrock Guardrails API. |
