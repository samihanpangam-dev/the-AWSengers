'use client'

import { useState } from 'react'
import { FileUploadSidebar } from '@/components/file-upload-sidebar'
import { ChatPanel } from '@/components/chat-panel'
import { getFileKind, type UploadedFile } from '@/lib/files'

// ── Types ─────────────────────────────────────────────────────────────────────

/**
 * Pairs the display metadata (UploadedFile) with the raw File object so the
 * chat panel can append the real binary to the FormData request.
 */
interface ManagedFile {
  meta: UploadedFile
  raw: File | null // null for the sample/placeholder entries
}

// ── Sample placeholder data ───────────────────────────────────────────────────
// Shown on first load so the UI never looks empty.  These have no raw File
// object — the backend call skips them gracefully (only real Files are sent).

const SAMPLE_MANAGED: ManagedFile[] = [
  {
    meta: { id: '1', name: 'quarterly-report.pdf', size: 2_411_000, kind: 'pdf' },
    raw: null,
  },
  {
    meta: { id: '2', name: 'product-demo.mp4', size: 48_200_000, kind: 'video' },
    raw: null,
  },
  {
    meta: { id: '3', name: 'interview.mp3', size: 8_700_000, kind: 'audio' },
    raw: null,
  },
]

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Page() {
  const [managed, setManaged] = useState<ManagedFile[]>(SAMPLE_MANAGED)

  /** The display-only list the sidebar renders. */
  const files: UploadedFile[] = managed.map((m) => m.meta)

  /** The real File objects forwarded to the chat panel for the API call. */
  const rawFiles: File[] = managed.flatMap((m) => (m.raw ? [m.raw] : []))

  function handleAddFiles(incoming: FileList | File[]) {
    const next: ManagedFile[] = Array.from(incoming).map((file) => ({
      meta: {
        id: crypto.randomUUID(),
        name: file.name,
        size: file.size,
        kind: getFileKind(file.name),
      },
      raw: file,
    }))
    setManaged((prev) => [...next, ...prev])
  }

  function handleRemoveFile(id: string) {
    setManaged((prev) => prev.filter((m) => m.meta.id !== id))
  }

  return (
    <div className="flex min-h-screen flex-col md:h-screen md:flex-row md:overflow-hidden">
      <FileUploadSidebar
        files={files}
        onAddFiles={handleAddFiles}
        onRemoveFile={handleRemoveFile}
      />
      <ChatPanel fileCount={files.length} rawFiles={rawFiles} />
    </div>
  )
}
