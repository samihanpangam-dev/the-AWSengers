# Design — Omni-File AI Agent

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (Next.js 16 / React 19)                                │
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────────────────┐  │
│  │ FileUploadSidebar│        │        ChatPanel             │  │
│  │  • Drag & drop   │        │  • Message history           │  │
│  │  • File list UI  │        │  • Textarea input            │  │
│  └────────┬─────────┘        └──────────────┬───────────────┘  │
│           │  files[]                         │ prompt           │
│           └──────────────┬───────────────────┘                 │
│                          │  multipart/form-data POST            │
│                          │  POST /process                       │
└──────────────────────────┼──────────────────────────────────────┘
                           │
         ┌─────────────────▼──────────────────────┐
         │  FastAPI  (uvicorn, port 8000)          │
         │  CORS: localhost:3000 / 3001            │
         │                                        │
         │  POST /process                         │
         │    1. Save uploads → /tmp/<uuid>/      │
         │    2. Build prompt + file context      │
         │    3. Invoke Strands Agent             │
         │    4. Return { response: string }      │
         └─────────────────┬──────────────────────┘
                           │
         ┌─────────────────▼──────────────────────┐
         │  BedrockAgentCoreApp wrapper            │
         │  (provides execution environment)       │
         └─────────────────┬──────────────────────┘
                           │
         ┌─────────────────▼──────────────────────┐
         │  Strands Agent                          │
         │  LLM: ollama/llama3 (local)             │
         │                                        │
         │  System Prompt (abridged):             │
         │  "You are a file transformation        │
         │   agent. Use merge_pdf, compress_video │
         │   or strip_audio for known tasks.      │
         │   Run all generated code through       │
         │   mock_guardrail before execution.     │
         │   Fallback: AgentCoreCodeInterpreter." │
         │                                        │
         │  Tools:                                │
         │  ┌──────────────────────────────────┐  │
         │  │ merge_pdf          (fast-path)   │  │
         │  │ compress_video     (fast-path)   │  │
         │  │ strip_audio        (fast-path)   │  │
         │  │ AgentCoreCodeInterpreter(fallback)│  │
         │  └──────────────────────────────────┘  │
         │                                        │
         │  Guardrail Gate (inline):              │
         │  mock_apply_guardrail(code) →          │
         │    NONE → proceed                      │
         │    GUARDRAIL_INTERVENED → block        │
         └────────────────────────────────────────┘
```

---

## 2. Backend Module Layout

```
backend/
├── main.py                  # FastAPI app, CORS, /process endpoint
├── agent.py                 # Strands Agent init + BedrockAgentCoreApp
├── guardrail.py             # mock_apply_guardrail()
├── config.py                # Centralised config (model, origins, paths)
├── tools/
│   ├── __init__.py
│   ├── merge_pdf.py         # @tool merge_pdf
│   ├── compress_video.py    # @tool compress_video
│   └── strip_audio.py       # @tool strip_audio
└── requirements.txt
```

---

## 3. Component Design

### 3.1 `config.py`

```python
OLLAMA_MODEL     = "ollama/llama3"
OLLAMA_BASE_URL  = "http://localhost:11434"
CORS_ORIGINS     = ["http://localhost:3000", "http://localhost:3001"]
UPLOAD_TMP_DIR   = "/tmp/omni_agent"
```

### 3.2 `guardrail.py`

```
mock_apply_guardrail(code_snippet: str) -> dict
  BLOCKED_PATTERNS = ["AKIA", "ignore all previous instructions"]
  for pattern in BLOCKED_PATTERNS:
      if pattern in code_snippet:
          return {"action": "GUARDRAIL_INTERVENED"}
  return {"action": "NONE"}
```

### 3.3 `tools/merge_pdf.py`

```
@tool
merge_pdf(pdf_paths: list[str], output_path: str) -> str
  doc = fitz.open()
  for path in pdf_paths:
      doc.insert_pdf(fitz.open(path))
  doc.save(output_path)
  return output_path
```

### 3.4 `tools/compress_video.py`

```
@tool
compress_video(input_path: str, output_path: str) -> str
  ffmpeg.input(input_path)
        .output(output_path, vcodec="libx264", crf=28, preset="fast")
        .overwrite_output()
        .run(quiet=True)
  return output_path
```

### 3.5 `tools/strip_audio.py`

```
@tool
strip_audio(input_path: str, output_path: str) -> str
  ffmpeg.input(input_path)
        .output(output_path, acodec="libmp3lame", audio_bitrate="192k", vn=None)
        .overwrite_output()
        .run(quiet=True)
  return output_path
```

### 3.6 `agent.py`

```
AgentCoreCodeInterpreter attached as a tool.

System prompt instructs:
  1. Use fast-path tools first.
  2. Pass any generated code through mock_apply_guardrail.
  3. If GUARDRAIL_INTERVENED → abort, report to user.
  4. If no dedicated tool fits → use AgentCoreCodeInterpreter.

BedrockAgentCoreApp(agent=agent) wraps the Strands Agent.
```

### 3.7 `main.py` — `/process` endpoint

```
POST /process
  Body (multipart/form-data):
    prompt  : str
    files[] : UploadFile[]

  Steps:
    1. Create /tmp/omni_agent/<uuid>/ directory.
    2. Save each UploadFile to disk.
    3. Build enriched prompt: include file names + paths.
    4. agent(enriched_prompt) → response string.
    5. Cleanup temp directory.
    6. Return {"response": response}

  Error handling:
    - GuardrailException  → 400 {"detail": "Guardrail blocked execution: <reason>"}
    - General Exception   → 500 {"detail": "Agent error: <message>"}
```

---

## 4. Request / Response Data Flow

```
Browser
  │
  │  POST /process
  │  Content-Type: multipart/form-data
  │  ┌─────────────────────────────────┐
  │  │ prompt = "Merge these PDFs"     │
  │  │ files  = [file1.pdf, file2.pdf] │
  │  └─────────────────────────────────┘
  │
FastAPI /process handler
  │  → saves files to /tmp/omni_agent/<uuid>/file1.pdf, file2.pdf
  │  → enriched_prompt = "User says: Merge these PDFs\nFiles: [...]"
  │
Strands Agent (ollama/llama3)
  │  → selects tool: merge_pdf
  │  → calls merge_pdf(["...file1.pdf","...file2.pdf"], "...merged.pdf")
  │
merge_pdf tool
  │  → uses fitz to merge → returns output_path
  │
Agent
  │  → composes final text response
  │
FastAPI handler
  │  → cleanup /tmp/omni_agent/<uuid>/
  │  → return {"response": "Done! Merged 2 PDFs → merged.pdf"}
  │
Browser
  │  → ChatPanel appends assistant message
```

---

## 5. Guardrail Decision Flow

```
Agent wants to execute code_snippet
        │
        ▼
mock_apply_guardrail(code_snippet)
        │
   ┌────┴────┐
   │ NONE    │ ──────────────────────────► Execute code
   └─────────┘
   │ GUARDRAIL_INTERVENED │ ──────────► Raise GuardrailException
                                         → FastAPI returns 400
                                         → ChatPanel shows error
```

---

## 6. Frontend Integration Points

The existing `ChatPanel` needs two changes:
1. Accept `files: UploadedFile[]` as a prop (currently only receives `fileCount`).
2. Replace the `window.setTimeout` mock with a real `fetch()` call to `POST /process`.

The `FileUploadSidebar` already holds the real `File` objects in its drag/drop handler — `page.tsx` needs to store the raw `File[]` alongside the `UploadedFile[]` metadata so they can be appended to the `FormData`.

---

## 7. Dependencies

### Python (backend/requirements.txt)
| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP framework |
| `uvicorn[standard]` | ASGI server |
| `python-multipart` | Multipart form parsing |
| `strands-agents` | Agent orchestration |
| `bedrock-agentcore` | AgentCoreCodeInterpreter + BedrockAgentCoreApp |
| `pymupdf` | PDF merge (fitz) |
| `ffmpeg-python` | Video/audio processing |
| `ollama` | Ollama Python client (LLM provider) |

### JavaScript (already in package.json)
- Next.js 16, React 19, Tailwind CSS, shadcn — no new deps required.
