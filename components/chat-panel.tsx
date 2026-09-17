'use client'

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowUp, Bot, Terminal, User, Wifi, WifiOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AgentApiError, pingBackend, processFiles } from '@/lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'welcome',
    role: 'assistant',
    content:
      "Hi! I'm your Omni-File agent. Drop a PDF, video, audio, or image in the sidebar and ask me anything about it — I'll run a code interpreter to analyse it.",
  },
]

// ── Component ─────────────────────────────────────────────────────────────────

interface ChatPanelProps {
  fileCount: number
  /**
   * Real File objects from the sidebar, forwarded to the API call.
   * Empty array when only placeholder / sample files are loaded.
   */
  rawFiles: File[]
}

export function ChatPanel({ fileCount, rawFiles }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES)
  const [input, setInput] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null) // null = checking
  const scrollRef = useRef<HTMLDivElement>(null)

  // ── Backend liveness probe ─────────────────────────────────────────────────
  // Runs once on mount so the header badge reflects real connectivity.
  useEffect(() => {
    pingBackend().then(setBackendOnline)
  }, [])

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isProcessing])

  // ── Submit handler ─────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isProcessing) return

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsProcessing(true)

    try {
      // ── Real API call ──────────────────────────────────────────────────────
      // Sends prompt + all real File objects as multipart/form-data.
      const reply = await processFiles(text, rawFiles)

      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'assistant', content: reply },
      ])
      // Mark backend as online after a successful call.
      setBackendOnline(true)
    } catch (err) {
      // ── Error handling ─────────────────────────────────────────────────────
      let errorText: string

      if (err instanceof AgentApiError) {
        // HTTP 4xx / 5xx with a detail string from FastAPI.
        errorText =
          err.status === 400
            ? `🛡️ Guardrail blocked: ${err.detail}`
            : `Server error (${err.status}): ${err.detail}`
      } else if (err instanceof TypeError && (err.message.includes('fetch') || err.message.includes('Failed'))) {
        // Network failure — backend unreachable.
        errorText =
          'Cannot reach the backend. Make sure `uvicorn backend.main:app --reload --port 8000` is running.'
        setBackendOnline(false)
      } else {
        errorText = `Unexpected error: ${err instanceof Error ? err.message : String(err)}`
      }

      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'error', content: errorText },
      ])
    } finally {
      setIsProcessing(false)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <main className="flex min-h-0 flex-1 flex-col bg-background">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Bot className="size-5" aria-hidden="true" />
          </span>
          <div className="leading-tight">
            <h1 className="text-sm font-semibold">Omni-File AI Agent</h1>
            <BackendStatusLine online={backendOnline} />
          </div>
        </div>
        <span className="hidden rounded-full border border-border bg-muted/40 px-3 py-1 text-xs text-muted-foreground sm:inline">
          {fileCount} asset{fileCount === 1 ? '' : 's'} loaded
        </span>
      </header>

      {/* ── Offline warning banner ──────────────────────────────────────────── */}
      {backendOnline === false && (
        <div
          role="alert"
          className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
        >
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
          Backend offline — run{' '}
          <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/60">
            uvicorn backend.main:app --reload --port 8000
          </code>{' '}
          to enable agent responses.
        </div>
      )}

      {/* ── Message list ───────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 md:px-6">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isProcessing && <ProcessingBubble />}
        </div>
      </div>

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <div className="sticky bottom-0 border-t border-border bg-background/80 backdrop-blur">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-4 md:px-6"
        >
          <div className="flex flex-1 items-end rounded-2xl border border-border bg-card px-3 py-2 transition-colors focus-within:border-primary/70 focus-within:ring-3 focus-within:ring-ring/30">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  handleSubmit(e)
                }
              }}
              rows={1}
              placeholder="Ask about your uploaded files…"
              className="max-h-40 min-h-6 w-full resize-none bg-transparent text-sm leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          <Button
            type="submit"
            size="icon-lg"
            aria-label="Send message"
            disabled={!input.trim() || isProcessing}
            className="rounded-full"
          >
            <ArrowUp />
          </Button>
        </form>
      </div>
    </main>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function BackendStatusLine({ online }: { online: boolean | null }) {
  if (online === null) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground/60" />
        Checking backend…
      </p>
    )
  }
  return online ? (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="size-1.5 rounded-full bg-emerald-400" />
      <Wifi className="size-3" aria-hidden="true" />
      Agent online
    </p>
  ) : (
    <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
      <span className="size-1.5 rounded-full bg-amber-400" />
      <WifiOff className="size-3" aria-hidden="true" />
      Backend offline
    </p>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const isError = message.role === 'error'

  if (isError) {
    return (
      <div
        role="alert"
        className="flex items-start gap-3"
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-amber-300 bg-amber-50 text-amber-600 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-400">
          <AlertTriangle className="size-4" aria-hidden="true" />
        </span>
        <div className="max-w-[80%] rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm leading-relaxed text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${
          isUser
            ? 'bg-primary/15 text-primary'
            : 'border border-border bg-card text-muted-foreground'
        }`}
      >
        {isUser ? (
          <User className="size-4" aria-hidden="true" />
        ) : (
          <Bot className="size-4" aria-hidden="true" />
        )}
      </span>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'border border-border bg-card text-card-foreground'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}

function ProcessingBubble() {
  return (
    <div className="flex items-start gap-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-primary">
        <Terminal className="size-4" aria-hidden="true" />
      </span>
      <div className="w-full max-w-[80%] rounded-2xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <span className="size-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          <span>Executing Code Interpreter to process your file…</span>
        </div>
        <div className="mt-3 space-y-2">
          <div className="h-2.5 w-4/5 animate-pulse rounded bg-muted" />
          <div className="h-2.5 w-3/5 animate-pulse rounded bg-muted" />
          <div className="h-2.5 w-2/3 animate-pulse rounded bg-muted" />
        </div>
      </div>
    </div>
  )
}
