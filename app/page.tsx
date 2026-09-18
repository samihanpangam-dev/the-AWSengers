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
  raw: File
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Page() {
  const [managed, setManaged] = useState<ManagedFile[]>([])

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

  function handleClearAll() {
    setManaged([])
  }

  return (
    <div className="flex min-h-screen flex-col md:h-screen md:flex-row md:overflow-hidden">
      <FileUploadSidebar
        files={files}
        onAddFiles={handleAddFiles}
        onRemoveFile={handleRemoveFile}
        onClearAll={handleClearAll}
      />
      <ChatPanel
        fileCount={files.length}
        rawFiles={rawFiles}
        onClearAll={handleClearAll}
      />
    </div>
  )
}
