'use client'

import { useRef, useState } from 'react'
import { UploadCloud, X, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  FileTypeIcon,
  formatBytes,
  getFileKind,
  type UploadedFile,
} from '@/lib/files'

type FileUploadSidebarProps = {
  files: UploadedFile[]
  onAddFiles: (files: FileList | File[]) => void
  onRemoveFile: (id: string) => void
  onClearAll?: () => void
}

export function FileUploadSidebar({
  files,
  onAddFiles,
  onRemoveFile,
  onClearAll,
}: FileUploadSidebarProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files?.length) {
      onAddFiles(e.dataTransfer.files)
    }
  }

  return (
    <aside className="flex w-full flex-col border-b border-sidebar-border bg-sidebar md:h-screen md:w-[300px] md:shrink-0 md:border-r md:border-b-0">
      <div className="flex items-center gap-2 px-5 py-4">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Sparkles className="size-4" aria-hidden="true" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold">Omni-File Agent</p>
          <p className="text-xs text-muted-foreground">Asset workspace</p>
        </div>
      </div>

      <div className="px-5 pb-4">
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              inputRef.current?.click()
            }
          }}
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
            isDragging
              ? 'border-primary bg-primary/10'
              : 'border-border bg-background/40 hover:border-primary/60 hover:bg-primary/5'
          }`}
        >
          <span className="flex size-11 items-center justify-center rounded-full bg-primary/15 text-primary">
            <UploadCloud className="size-5" aria-hidden="true" />
          </span>
          <div className="space-y-1">
            <p className="text-sm font-medium">Drop Assets Here</p>
            <p className="text-xs text-muted-foreground">
              PDF, MP4, MP3, JPG
            </p>
          </div>
          <span className="text-[11px] text-muted-foreground/80">
            or click to browse
          </span>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="sr-only"
            accept=".pdf,.mp4,.mp3,.jpg,.jpeg,.png,.wav,.mov,.webm"
            onChange={(e) => {
              if (e.target.files?.length) onAddFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-5 pb-5">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Uploaded Files
            </h2>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              {files.length}
            </span>
          </div>
          {files.length > 1 && onClearAll && (
            <button
              type="button"
              onClick={onClearAll}
              className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-destructive"
              title="Clear all files"
            >
              <Trash2 className="size-3" />
              <span>Clear All</span>
            </button>
          )}
        </div>

        {files.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border/60 px-4 py-8 text-center">
            <p className="text-xs text-muted-foreground">
              No files yet. Uploaded assets will appear here.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-1.5 overflow-y-auto md:max-h-[calc(100vh-320px)]">
            {files.map((file) => (
              <li
                key={file.id}
                className="group flex items-center gap-3 rounded-lg border border-border/60 bg-background/40 px-2.5 py-2 transition-colors hover:border-border hover:bg-background/70"
              >
                <FileTypeIcon kind={file.kind} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {formatBytes(file.size)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => onRemoveFile(file.id)}
                  className="text-muted-foreground opacity-60 hover:text-foreground group-hover:opacity-100"
                >
                  <X />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
