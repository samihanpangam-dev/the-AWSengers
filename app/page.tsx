'use client'

import { useState } from 'react'
import { FileUploadSidebar } from '@/components/file-upload-sidebar'
import { ChatPanel } from '@/components/chat-panel'
import { getFileKind, type UploadedFile } from '@/lib/files'

const SAMPLE_FILES: UploadedFile[] = [
  { id: '1', name: 'quarterly-report.pdf', size: 2_411_000, kind: 'pdf' },
  { id: '2', name: 'product-demo.mp4', size: 48_200_000, kind: 'video' },
  { id: '3', name: 'interview.mp3', size: 8_700_000, kind: 'audio' },
]

export default function Page() {
  const [files, setFiles] = useState<UploadedFile[]>(SAMPLE_FILES)

  function handleAddFiles(incoming: FileList | File[]) {
    const next = Array.from(incoming).map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      kind: getFileKind(file.name),
    }))
    setFiles((prev) => [...next, ...prev])
  }

  function handleRemoveFile(id: string) {
    setFiles((prev) => prev.filter((file) => file.id !== id))
  }

  return (
    <div className="flex min-h-screen flex-col md:h-screen md:flex-row md:overflow-hidden">
      <FileUploadSidebar
        files={files}
        onAddFiles={handleAddFiles}
        onRemoveFile={handleRemoveFile}
      />
      <ChatPanel fileCount={files.length} />
    </div>
  )
}
