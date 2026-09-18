/**
 * api.ts — Omni-File Agent API client
 *
 * All communication with the FastAPI backend goes through this module.
 * The backend URL is read from the environment variable NEXT_PUBLIC_API_URL,
 * which is set per-environment:
 *
 *   Local dev    →  .env.local                       → http://localhost:8000
 *   Vercel prod  →  Vercel dashboard env var         → https://<tunnel>.trycloudflare.com
 *
 * No component ever hardcodes a URL.
 */

// Strip trailing slash so callers never need to worry about double-slashes.
export const BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
).replace(/\/$/, '')

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ProcessResponse {
  response: string
  files?: string[]
  download_url?: string
}

/**
 * Thrown when the backend replies with a non-2xx HTTP status.
 * Carries the status code and FastAPI's `detail` string.
 */
export class AgentApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail)
    this.name = 'AgentApiError'
  }
}

/**
 * Thrown when the network request fails entirely — tunnel down, Mac asleep,
 * no internet, etc.  Distinct from AgentApiError so the UI can show a
 * different, more actionable message.
 */
export class BackendUnreachableError extends Error {
  constructor(cause?: unknown) {
    super('Backend is unreachable')
    this.name = 'BackendUnreachableError'
    if (cause instanceof Error) this.cause = cause
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns true if the error looks like a network-level failure:
 * fetch() TypeError, AbortError from timeout, or a Cloudflare 5xx tunnel page.
 */
function isNetworkFailure(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true
  if (err instanceof TypeError) return true
  return false
}

// ── Health check ──────────────────────────────────────────────────────────────

/**
 * Ping GET /health.  Returns true if the backend is reachable and healthy.
 * Used on mount to drive the status indicator in the header.
 *
 * Times out after 5 seconds — long enough to handle a cold tunnel wake-up.
 */
export async function pingBackend(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`, {
      method: 'GET',
      // Cloudflare tunnels occasionally need a few extra seconds on first hit.
      signal: AbortSignal.timeout(5_000),
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
 * Sent as `multipart/form-data` — do NOT set Content-Type manually.
 * The browser sets it automatically (including the boundary) when body is FormData.
 *
 * @param prompt  Natural-language instruction for the agent.
 * @param files   Raw File objects from drag-and-drop / file-picker.
 *                Pass [] for text-only queries.
 *
 * @returns An object with the agent's textual reply string and an optional downloadUrl.
 *
 * @throws {BackendUnreachableError}  Network failure / tunnel down / Mac asleep.
 * @throws {AgentApiError}            Backend returned 4xx or 5xx.
 */
export async function processFiles(
  prompt: string,
  files: File[],
  signal?: AbortSignal,
): Promise<{ reply: string; files: string[]; downloadUrl?: string }> {
  const body = new FormData()
  body.append('prompt', prompt)
  for (const file of files) {
    // Append under the field name "files" to match the FastAPI parameter name.
    body.append('files', file, file.name)
  }

  let res: Response
  try {
    res = await fetch(`${BASE_URL}/process`, {
      method: 'POST',
      body,
      signal,
      // No explicit timeout here — file processing can take 10-30 s.
      // The processing bubble in the UI communicates progress to the user.
    })
  } catch (err) {
    // fetch() itself threw — network is down, tunnel is closed, CORS preflight
    // hard-failed, or the Mac went to sleep mid-request.
    if (isNetworkFailure(err)) {
      throw new BackendUnreachableError(err)
    }
    throw err
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const json = (await res.json()) as { detail?: string }
      detail = json.detail ?? detail
    } catch {
      // Non-JSON error body — keep the status string.
    }
    throw new AgentApiError(res.status, detail)
  }

  const data = (await res.json()) as ProcessResponse
  const fileList = Array.isArray(data.files) && data.files.length > 0
    ? data.files
    : data.download_url
      ? [data.download_url]
      : []
  return { reply: cleanReplyText(data.response), files: fileList, downloadUrl: data.download_url }
}

function cleanReplyText(text: string): string {
  if (!text) return ''
  const trimmed = text.trim()
  if (trimmed.startsWith('{') && trimmed.includes('"message"')) {
    try {
      const parsed = JSON.parse(trimmed)
      if (parsed && typeof parsed.message === 'string') {
        return parsed.message
      }
    } catch {
      const match = trimmed.match(/"message"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/)
      if (match && match[1]) {
        return match[1].replace(/\\"/g, '"').replace(/\\n/g, '\n')
      }
    }
  }
  return text
}
