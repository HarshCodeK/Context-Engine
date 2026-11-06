import { useRef } from 'react'
import { IconArrowUpRight, IconUpload } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import type { UploadConfig } from '@/lib/types'
import { formatBytes } from '@/lib/format'

type Props = {
  config: UploadConfig
  dragging: boolean
  onFiles: (files: FileList | File[]) => void
  onDragChange: (dragging: boolean) => void
}

export function UploadDropzone({ config, dragging, onFiles, onDragChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const formats = ['PDF', 'DOCX', 'PPTX', 'XLSX', 'CSV', 'MD', 'TXT', 'JSON', 'HTML', 'IMAGES']
  const accept = config.supported_extensions.map((extension) => `.${extension.replace(/^\./, '')}`).join(',')

  return (
    <Card
      className={`upload-zone ${dragging ? 'is-dragging' : ''}`}
      onDragEnter={(event) => { event.preventDefault(); onDragChange(true) }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) onDragChange(false)
      }}
      onDrop={(event) => {
        event.preventDefault()
        onDragChange(false)
        onFiles(event.dataTransfer.files)
      }}
    >
      <CardContent className="upload-content">
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept={accept}
          aria-label="Choose source documents"
          onChange={(event) => {
            if (event.target.files?.length) onFiles(event.target.files)
            event.target.value = ''
          }}
        />
        <div className="upload-symbol" aria-hidden="true"><IconUpload size={25} stroke={1.5} /></div>
        <div className="upload-copy">
          <h2>Bring your source material.</h2>
          <p>Drop files here or choose them from your device. Processing stays on this machine.</p>
        </div>
        <div className="upload-formats" aria-label="Supported formats">
          {formats.map((format) => <Badge key={format} variant="outline">{format}</Badge>)}
        </div>
        <Button onClick={() => inputRef.current?.click()}>
          Choose files <IconArrowUpRight data-icon="inline-end" size={16} />
        </Button>
        <p className="upload-limits">
          Up to {config.max_files} files <span>·</span> {formatBytes(config.max_file_bytes)} per file <span>·</span> {formatBytes(config.max_batch_bytes)} per batch
        </p>
      </CardContent>
    </Card>
  )
}
