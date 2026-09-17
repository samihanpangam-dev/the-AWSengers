/**
 * api.ts — Omni-File Agent API client
 *
 * Encapsulates all communication with the FastAPI backend so components
 * never construct fetch() calls directly.  Swap the BASE_URL constant to
 * point at a staging or production endpoint without touching any component.
 */

const BASE_URL = process.env.NEXT_PUBLIC_AGENT_API_URL ?? 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ProcessResponse {
  response: string
}

/** Structured error returned when the backend replies with a non-2xx status. */
export class AgentApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail)
    this.name = 'AgentApiError'
  }
}

// ── Health check ──────────────────────────────────────────────────────────────

/**
 * Ping GET /health to check whether the backend is reachable.
 *
 * @returns `true` if the backend responds OK, `false` on any error.
 */
export async function pingBackend(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3_000), // 3-second timeout
    })
    return res.ok
  } catch {
    return false
  }
}

// ── Main endpoint ─────────────────────────────────────────────────────────────

/**
 * Send a prompt and zero-or-more files to POST /process.
 *
 * The request is sent as `multipart/form-data` — *never* set the
 * Content-Type header manually; the browser must set it so the boundary
 * parameter is included automatically.
 *
 * @param prompt  - Natural-language instruction from the user.
 * @param files   - Raw File objects from the drag-and-drop / file-picker.
 *                  Pass an empty array for text-only queries.
 *
 * @returns The agent's textual reply.
 *
 * @throws {AgentApiError}  When the backend returns 4xx or 5xx.
 * @throws {Error}          On network failure (no connection, CORS, timeout).
 *
 * @example
 * ```ts
 * const reply = await processFiles('Merge all the PDFs', rawFiles)
 * console.log(reply) // "Done! Merged 3 PDFs → merged.pdf"
 * ```
 */
export async function processFiles(
  prompt: string,
  files: File[],
): Promise<string> {
  const body = new FormData()

  // Field names must match the FastAPI endpoint parameter names exactly.
  body.append('prompt', prompt)
  for (const file of files) {
    body.append('files', file, file.name)
  }

  const res = await fetch(`${BASE_URL}/process`, {
    method: 'POST',
    // ⚠️  Do NOT set Content-Type here — the browser adds the multipart
    //     boundary automatically when body is a FormData instance.
    body,
  })

  if (!res.ok) {
    // FastAPI error bodies follow { "detail": string }
    let detail = `HTTP ${res.status}`
    try {
      const json = (await res.json()) as { detail?: string }
      detail = json.detail ?? detail
    } catch {
      // response body wasn't JSON — keep the status string
    }
    throw new AgentApiError(res.status, detail)
  }

  const data = (await res.json()) as ProcessResponse
  return data.response
}
