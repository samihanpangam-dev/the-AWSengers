# Tasks — Omni-File AI Agent

Each task maps to one or more files. Tasks are ordered so that later tasks never depend on incomplete earlier ones.

---

## Phase 1 · Python Backend Scaffolding

### Task 1 — Create `backend/requirements.txt`
- [ ] Add all Python dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `strands-agents`, `bedrock-agentcore`, `pymupdf`, `ffmpeg-python`, `ollama`.

### Task 2 — Create `backend/config.py`
- [ ] Define `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `CORS_ORIGINS`, `UPLOAD_TMP_DIR`.

### Task 3 — Create `backend/guardrail.py`
- [ ] Implement `mock_apply_guardrail(code_snippet: str) -> dict`.
- [ ] Block on `"AKIA"` and `"ignore all previous instructions"`.
- [ ] Define `GuardrailException` for clean exception propagation.

---

## Phase 2 · Dedicated Tools

### Task 4 — Create `backend/tools/__init__.py`
- [ ] Export `merge_pdf`, `compress_video`, `strip_audio` for easy import.

### Task 5 — Create `backend/tools/merge_pdf.py`
- [ ] Implement `@tool merge_pdf(pdf_paths, output_path)` using PyMuPDF `fitz`.
- [ ] Validate that all input paths exist before processing.
- [ ] Return the output path string on success.

### Task 6 — Create `backend/tools/compress_video.py`
- [ ] Implement `@tool compress_video(input_path, output_path)` using `ffmpeg-python`.
- [ ] Use `vcodec="libx264"`, `crf=28`, `preset="fast"`.
- [ ] Return the output path string on success.

### Task 7 — Create `backend/tools/strip_audio.py`
- [ ] Implement `@tool strip_audio(input_path, output_path)` using `ffmpeg-python`.
- [ ] Use `acodec="libmp3lame"`, `audio_bitrate="192k"`, `vn=None` to drop video.
- [ ] Return the output path string on success.

---

## Phase 3 · Agent Assembly

### Task 8 — Create `backend/agent.py`
- [ ] Import all three tools and `AgentCoreCodeInterpreter`.
- [ ] Write the system prompt string covering: fast-path priority, guardrail gate, code-interpreter fallback.
- [ ] Instantiate `Agent` with `model=OLLAMA_MODEL`, `tools=[merge_pdf, compress_video, strip_audio, interpreter]`, and the system prompt.
- [ ] Wrap with `BedrockAgentCoreApp(agent=agent)`.
- [ ] Export both `agent` and `agent_app` for use in `main.py`.

---

## Phase 4 · FastAPI Server

### Task 9 — Create `backend/main.py`
- [ ] Initialise FastAPI app with `CORSMiddleware` using `CORS_ORIGINS`.
- [ ] Implement `POST /process` accepting `prompt: str = Form(...)` and `files: list[UploadFile] = File(...)`.
- [ ] Save each upload to a UUID-scoped temp directory under `UPLOAD_TMP_DIR`.
- [ ] Build an enriched prompt string that includes file names and disk paths.
- [ ] Call `agent(enriched_prompt)` and capture the response.
- [ ] Clean up the temp directory in a `finally` block.
- [ ] Return `{"response": str(result)}`.
- [ ] Handle `GuardrailException` → HTTP 400.
- [ ] Handle all other exceptions → HTTP 500.
- [ ] Add a `GET /health` endpoint returning `{"status": "ok"}`.

---

## Phase 5 · Frontend Integration

### Task 10 — Update `app/page.tsx`
- [ ] Add `rawFiles` state (`File[]`) alongside the existing `files` (`UploadedFile[]`) state.
- [ ] Update `handleAddFiles` to also push the original `File` objects into `rawFiles`.
- [ ] Update `handleRemoveFile` to remove the corresponding raw `File` object by index/id alignment.
- [ ] Pass `rawFiles` down to `ChatPanel` as a new `files` prop.

### Task 11 — Update `components/chat-panel.tsx`
- [ ] Add `files: File[]` to the `ChatPanel` props type.
- [ ] Replace the `window.setTimeout` mock with a real `async` submit handler.
- [ ] Build a `FormData` object with `prompt` and each `File` appended as `files`.
- [ ] `fetch("http://localhost:8000/process", { method: "POST", body: formData })`.
- [ ] Parse the JSON response `{ response: string }` and append the assistant message.
- [ ] On network or HTTP error, append a user-facing error message instead of crashing.
- [ ] Add a `GET /health` preflight ping on mount and show a warning badge if the backend is unreachable.

### Task 12 — Create `components/api.ts` (optional utility)
- [ ] Export `processFiles(prompt, files)` encapsulating the `fetch` call for reuse and testability.

---

## Phase 6 · Verification

### Task 13 — Smoke test the backend
- [ ] Run `uvicorn backend.main:app --reload --port 8000`.
- [ ] `curl -F "prompt=merge all pdfs" -F "files=@test.pdf" http://localhost:8000/process` and verify JSON response.
- [ ] Test guardrail: send a prompt containing "AKIA" and verify HTTP 400.

### Task 14 — Smoke test the frontend
- [ ] Run `pnpm dev`.
- [ ] Drop a PDF into the sidebar and type "merge the PDFs".
- [ ] Confirm the chat panel displays the agent's real response.
- [ ] Confirm the processing spinner appears and disappears correctly.

---

## Acceptance Criteria Checklist

| # | Criterion |
|---|-----------|
| AC-1 | `POST /process` returns `{"response": "..."}` for a valid file + prompt |
| AC-2 | Guardrail blocks requests containing `"AKIA"` with HTTP 400 |
| AC-3 | Guardrail blocks prompt-injection strings with HTTP 400 |
| AC-4 | `merge_pdf` tool merges two PDFs without LLM round-trip overhead |
| AC-5 | `compress_video` tool produces a smaller MP4 |
| AC-6 | `strip_audio` tool extracts an MP3 from an MP4 |
| AC-7 | Unknown file type falls back to `AgentCoreCodeInterpreter` |
| AC-8 | React frontend sends real `multipart/form-data` to the backend |
| AC-9 | CORS allows requests from `localhost:3000` and `localhost:3001` |
| AC-10 | Temp files are cleaned up after each request |
