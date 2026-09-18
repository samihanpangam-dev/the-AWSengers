'use client'

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowUp, Bot, Terminal, User, Wifi, WifiOff, Download, Trash2 } from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/button'
import { AgentApiError, BackendUnreachableError, pingBackend, processFiles, BASE_URL } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  downloadUrl?: string
  files?: string[]
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
  onClearAll?: () => void
}

export function ChatPanel({ fileCount, rawFiles, onClearAll }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES)
  const [input, setInput] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null) // null = checking
  const [showTrimmer, setShowTrimmer] = useState(false)
  const [trimPendingText, setTrimPendingText] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // ── Backend liveness probe ─────────────────────────────────────────────────
  // Runs once on mount, then every 30 s so the badge self-heals when the
  // tunnel comes back up without requiring a page refresh.
  useEffect(() => {
    pingBackend().then(setBackendOnline)
    const id = setInterval(() => pingBackend().then(setBackendOnline), 30_000)
    return () => clearInterval(id)
  }, [])

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isProcessing])

  const [abortController, setAbortController] = useState<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // ── Auto-expanding textarea height ─────────────────────────────────────────
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`
  }, [input])

  // ── Clear preview and trimmer state when files are cleared ──────────────────
  useEffect(() => {
    if (rawFiles.length === 0) {
      setShowTrimmer(false)
      setTrimPendingText('')
    }
  }, [rawFiles.length])

  function handleClearAll() {
    setShowTrimmer(false)
    setTrimPendingText('')
    onClearAll?.()
  }
  
function isMediaFile(file: File): boolean {
  if (file.type.startsWith('audio/') || file.type.startsWith('video/')) return true
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  return ['mp3', 'mp4', 'wav', 'm4a', 'aac', 'mov', 'mkv', 'flac', 'ogg', 'webm'].includes(ext)
}

function findMediaFile(files: File[]): File | undefined {
  return files.find(isMediaFile)
}

function hasTimeIndicators(text: string): boolean {
  // Matches timestamps with colons (e.g. 00:15, 01:30, 00:01:30, 1:45)
  if (/\b\d{1,2}:\d{2}(?::\d{2})?\b/.test(text)) return true

  // Matches numeric values with time units (e.g. 10s, 15 sec, 2 mins, 1 hour, 30seconds)
  if (/\b\d+\s*(?:s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)\b/i.test(text)) return true

  // Matches range patterns (e.g. "from 10 to 20", "between 5 and 15")
  if (/\b(?:from|between)\s+\S+\s+(?:to|and)\s+\S+/i.test(text)) return true

  // Matches boundary or position references (e.g. "start at 10", "end at 40", "first 30", "last 15")
  if (/\b(?:start(?:s|ing)?|end(?:s|ing)?|first|last)\s+(?:at\s+|from\s+)?\d+/i.test(text)) return true

  return false
}

  // ── Submit handler ─────────────────────────────────────────────────────────
  async function handleSubmit(e?: React.FormEvent, overrideText?: string) {
    if (e) e.preventDefault()
    const text = overrideText || input.trim()
    if (!text || isProcessing) return

    // ── Trimmer Interception ─────────────────────────────────────────────────
    // Only trigger the visual trimmer modal when the user requests a trim WITHOUT
    // already specifying explicit time/duration parameters in the prompt.
    const isTrimIntent = /\b(trim|cut)\b/i.test(text)
    const hasExplicitTimes = hasTimeIndicators(text)
    const mediaFile = findMediaFile(rawFiles)
    if (isTrimIntent && mediaFile && !hasExplicitTimes && !overrideText) {
      setTrimPendingText(text)
      setShowTrimmer(true)
      return
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsProcessing(true)
    
    const controller = new AbortController()
    setAbortController(controller)

    try {
      // ── Real API call ──────────────────────────────────────────────────────
      // Sends prompt + all real File objects as multipart/form-data.
      const { reply, files: resultFiles, downloadUrl } = await processFiles(text, rawFiles, controller.signal)

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: reply,
          files: resultFiles && resultFiles.length > 0 ? resultFiles : downloadUrl ? [downloadUrl] : undefined,
          downloadUrl,
        },
      ])
      // Mark backend as online after a successful call.
      setBackendOnline(true)
    } catch (err) {
      // ── Error handling ─────────────────────────────────────────────────────
      if (err instanceof DOMException && err.name === 'AbortError') {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: 'error', content: 'Generation cancelled by user.' },
        ])
        return
      }

      let errorText: string

      if (err instanceof BackendUnreachableError) {
        // Tunnel is down, Mac is asleep, or no internet.
        errorText =
          '🔌 Cannot reach the backend. The Cloudflare tunnel may be down or ' +
          'the Mac running the agent may be asleep. Ask the host to restart ' +
          'the tunnel, then try again.'
        setBackendOnline(false)
      } else if (err instanceof AgentApiError) {
        // HTTP 4xx / 5xx with a FastAPI detail string.
        errorText =
          err.status === 400
            ? `🛡️ Guardrail blocked: ${err.detail}`
            : `Server error (${err.status}): ${err.detail}`
      } else {
        errorText = `Unexpected error: ${err instanceof Error ? err.message : String(err)}`
      }

      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'error', content: errorText },
      ])
    } finally {
      setIsProcessing(false)
      setAbortController(null)
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
          className="flex items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
        >
          <span className="flex items-center gap-2">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
            Backend unreachable — the Cloudflare tunnel may be down or the host Mac is asleep.
          </span>
          <button
            onClick={() => pingBackend().then(setBackendOnline)}
            className="shrink-0 rounded border border-amber-300 bg-amber-100 px-2 py-0.5 font-medium hover:bg-amber-200 dark:border-amber-700 dark:bg-amber-900/50 dark:hover:bg-amber-900"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Message list ───────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto relative">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 md:px-6">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isProcessing && <ProcessingBubble />}
        </div>
      </div>

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <div className="sticky bottom-0 border-t border-border bg-background/80 backdrop-blur">
        {rawFiles.length > 0 && (
          <div className="mx-auto flex max-w-3xl items-center justify-between px-4 pt-3 pb-0 md:px-6">
            <div className="flex flex-1 items-center gap-2 overflow-hidden text-xs text-muted-foreground">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80 shrink-0">
                Queue ({rawFiles.length}):
              </span>
              <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto max-h-16 py-0.5">
                {rawFiles.map((file, idx) => (
                  <span
                    key={`${file.name}-${idx}`}
                    className="inline-flex items-center gap-1 rounded-md border border-border/70 bg-card px-2 py-0.5 text-xs font-medium text-foreground"
                    title={file.name}
                  >
                    <span className="max-w-[150px] truncate">{file.name}</span>
                  </span>
                ))}
              </div>
            </div>
            {rawFiles.length > 1 && onClearAll && (
              <button
                type="button"
                onClick={handleClearAll}
                className="ml-3 inline-flex shrink-0 items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-destructive"
                title="Clear all files in queue"
              >
                <Trash2 className="size-3.5" />
                <span>Clear All</span>
              </button>
            )}
          </div>
        )}
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-4 md:px-6"
        >
          <div className="flex flex-1 items-end rounded-2xl border border-border bg-card px-3 py-2 transition-colors focus-within:border-primary/70 focus-within:ring-3 focus-within:ring-ring/30">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  e.preventDefault()
                  handleSubmit(e)
                }
              }}
              rows={1}
              placeholder="Ask about your uploaded files…"
              className="max-h-48 min-h-[24px] w-full resize-none overflow-y-auto bg-transparent text-sm leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          {isProcessing ? (
            <Button
              type="button"
              size="icon-lg"
              variant="destructive"
              aria-label="Stop generation"
              onClick={() => abortController?.abort()}
              className="rounded-full shrink-0"
            >
              <div className="h-4 w-4 bg-current rounded-sm" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon-lg"
              aria-label="Send message"
              disabled={!input.trim()}
              className="rounded-full shrink-0"
            >
              <ArrowUp />
            </Button>
          )}
        </form>
      </div>

      {/* ── Visual Timeline Trimmer Overlay ────────────────────────────────── */}
      {showTrimmer && findMediaFile(rawFiles) && (
        <MediaTrimmerModal 
          file={findMediaFile(rawFiles)!}
          pendingPrompt={trimPendingText}
          onClose={() => setShowTrimmer(false)}
          onSkip={() => {
            const textToSend = trimPendingText
            setShowTrimmer(false)
            setTrimPendingText('')
            handleSubmit(undefined, textToSend)
          }}
          onSubmit={(start, end) => {
            const finalPrompt = `${trimPendingText} (trim range: ${start} to ${end})`
            setShowTrimmer(false)
            setTrimPendingText('')
            handleSubmit(undefined, finalPrompt)
          }}
        />
      )}
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
        <div className="whitespace-pre-wrap">{message.content}</div>
        {message.files && message.files.length > 0 ? (
          <div className="mt-3 flex flex-col items-start gap-2">
            {message.files && message.files.map((file, index) => <DownloadButton key={index} file={file} />)}
          </div>
        ) : message.downloadUrl ? (
          <div className="mt-3 flex flex-col items-start gap-2">
            <DownloadButton file={message.downloadUrl} />
          </div>
        ) : null}
      </div>
    </div>
  )
}

function DownloadButton({ file }: { file: string }) {
  const filename = decodeURIComponent(file.split('/').pop() || file)

  return (
    <a
      href={file.startsWith('http') ? file : `${BASE_URL}${file.startsWith('/') ? '' : '/'}${file}`}
      download={filename}
      className={cn(
        buttonVariants({ size: 'sm', variant: 'secondary' }),
        "gap-2 bg-secondary text-secondary-foreground hover:bg-secondary/80 inline-flex items-center text-xs font-medium max-w-full truncate shadow-sm transition-all"
      )}
    >
      <Download className="size-3.5 shrink-0" />
      <span className="truncate">Download {filename}</span>
    </a>
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

function MediaTrimmerModal({
  file,
  pendingPrompt,
  onClose,
  onSkip,
  onSubmit
}: {
  file: File;
  pendingPrompt?: string;
  onClose: () => void;
  onSkip?: () => void;
  onSubmit: (start: string, end: string) => void;
}) {
  const [duration, setDuration] = useState(0)
  const [start, setStart] = useState(0)
  const [end, setEnd] = useState(0)
  const [mediaUrl, setMediaUrl] = useState('')
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null)

  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    setMediaUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150">
         <div>
           <h2 className="text-lg font-semibold">Visual Media Trimmer</h2>
           <p className="text-xs text-muted-foreground truncate mt-0.5">File: {file?.name}</p>
           {pendingPrompt && (
             <p className="text-xs text-primary/80 truncate mt-0.5">Instruction: "{pendingPrompt}"</p>
           )}
         </div>
         
         {/* Live Preview */}
         <div className="relative w-full rounded-lg overflow-hidden bg-black/5 flex items-center justify-center" style={{ minHeight: 200 }}>
           {file?.type.startsWith('video/') ? (
             <video 
               ref={mediaRef} 
               src={mediaUrl} 
               controls 
               className="max-h-64 w-auto"
               onLoadedMetadata={(e) => {
                 setDuration(e.currentTarget.duration)
                 setEnd(e.currentTarget.duration)
               }}
               onTimeUpdate={(e) => {
                 if (e.currentTarget.currentTime > end) {
                   e.currentTarget.currentTime = start
                   e.currentTarget.pause()
                 }
               }}
             />
           ) : (
             <audio 
               ref={mediaRef} 
               src={mediaUrl} 
               controls 
               className="w-full mx-4"
               onLoadedMetadata={(e) => {
                 setDuration(e.currentTarget.duration)
                 setEnd(e.currentTarget.duration)
               }}
               onTimeUpdate={(e) => {
                 if (e.currentTarget.currentTime > end) {
                   e.currentTarget.currentTime = start
                   e.currentTarget.pause()
                 }
               }}
             />
           )}
         </div>

         {/* Sliders */}
         {duration > 0 && (
           <div className="space-y-4 mt-2">
             <div className="space-y-1.5">
               <div className="flex justify-between text-xs font-medium">
                 <span>Start: {formatTime(start)}</span>
               </div>
               <input 
                 type="range" 
                 min="0" 
                 max={end - 1} 
                 value={start} 
                 onChange={(e) => {
                   const val = Number(e.target.value)
                   setStart(val)
                   if (mediaRef.current) mediaRef.current.currentTime = val
                 }}
                 className="w-full accent-primary" 
               />
             </div>
             
             <div className="space-y-1.5">
               <div className="flex justify-between text-xs font-medium">
                 <span>End: {formatTime(end)}</span>
               </div>
               <input 
                 type="range" 
                 min={start + 1} 
                 max={duration} 
                 value={end} 
                 onChange={(e) => {
                   const val = Number(e.target.value)
                   setEnd(val)
                   if (mediaRef.current) mediaRef.current.currentTime = val
                 }}
                 className="w-full accent-primary" 
               />
             </div>
           </div>
         )}

          {/* Actions */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
             <Button variant="ghost" onClick={onClose}>Cancel</Button>
             <div className="flex items-center gap-2">
               {onSkip && (
                 <Button variant="outline" onClick={onSkip}>
                   Send Without Trimming
                 </Button>
               )}
               <Button onClick={() => onSubmit(formatTime(start), formatTime(end))}>
                 Trim & Send
               </Button>
             </div>
          </div>
       </div>
     </div>
  )
}
