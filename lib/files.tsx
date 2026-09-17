import { FileText, FileVideo, FileAudio, FileImage, File } from 'lucide-react'

export type UploadedFile = {
  id: string
  name: string
  size: number
  kind: FileKind
}

export type FileKind = 'pdf' | 'video' | 'audio' | 'image' | 'other'

export function getFileKind(name: string): FileKind {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'pdf') return 'pdf'
  if (['mp4', 'mov', 'webm', 'avi', 'mkv'].includes(ext)) return 'video'
  if (['mp3', 'wav', 'ogg', 'm4a', 'flac'].includes(ext)) return 'audio'
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) return 'image'
  return 'other'
}

const kindStyles: Record<FileKind, { icon: typeof File; className: string }> = {
  pdf: { icon: FileText, className: 'text-rose-400 bg-rose-500/10' },
  video: { icon: FileVideo, className: 'text-sky-400 bg-sky-500/10' },
  audio: { icon: FileAudio, className: 'text-emerald-400 bg-emerald-500/10' },
  image: { icon: FileImage, className: 'text-amber-400 bg-amber-500/10' },
  other: { icon: File, className: 'text-muted-foreground bg-muted' },
}

export function FileTypeIcon({
  kind,
  className,
}: {
  kind: FileKind
  className?: string
}) {
  const { icon: Icon, className: tone } = kindStyles[kind]
  return (
    <span
      className={`flex size-8 shrink-0 items-center justify-center rounded-md ${tone} ${className ?? ''}`}
    >
      <Icon className="size-4" aria-hidden="true" />
    </span>
  )
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}
