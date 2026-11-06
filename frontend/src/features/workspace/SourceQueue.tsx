import { IconAlertTriangle, IconCheck, IconFile, IconFileCode, IconFileSpreadsheet, IconFileTypePdf, IconPhoto, IconRefresh, IconX } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import type { ExtractionResult, ProcessingMode, QueuedSource } from '@/lib/types'
import { fileExtension, formatBytes } from '@/lib/format'

type Props = {
  sources: QueuedSource[]
  results: ExtractionResult[]
  activeId: string | null
  includedIds: string[]
  search: string
  mode: ProcessingMode
  busy: boolean
  canBuild: boolean
  onSearch: (value: string) => void
  onModeChange: (mode: ProcessingMode) => void
  onBuild: () => void
  onClear: () => void
  onSelect: (id: string) => void
  onRemove: (id: string) => void
  onRetry: (source: QueuedSource) => void
  onToggleInclude: (id: string) => void
}

function FileIcon({ filename }: { filename: string }) {
  const extension = fileExtension(filename)
  if (extension === 'pdf') return <IconFileTypePdf size={20} stroke={1.5} />
  if (['csv', 'xlsx'].includes(extension)) return <IconFileSpreadsheet size={20} stroke={1.5} />
  if (['png', 'jpg', 'jpeg', 'webp'].includes(extension)) return <IconPhoto size={20} stroke={1.5} />
  if (['json', 'html', 'htm'].includes(extension)) return <IconFileCode size={20} stroke={1.5} />
  if (extension === 'pptx') return <IconFile size={20} stroke={1.5} />
  return <IconFile size={20} stroke={1.5} />
}

export function SourceQueue({
  sources, results, activeId, includedIds, search, mode, busy, canBuild,
  onSearch, onModeChange, onBuild, onClear, onSelect, onRemove, onRetry, onToggleInclude,
}: Props) {
  const visibleSources = sources.filter((source) => source.file.name.toLowerCase().includes(search.toLowerCase()))
  const includedCount = includedIds.length

  return (
    <Card className="panel-card source-panel">
      <CardHeader className="panel-header">
        <div>
          <p className="eyebrow">01 / INPUT</p>
          <CardTitle>Source files <Badge variant="secondary">{sources.length}</Badge></CardTitle>
        </div>
        <div className="source-header-actions">
          <Badge variant="outline">{includedCount} in pack</Badge>
          <Button variant="ghost" size="sm" onClick={onClear} disabled={busy || sources.length === 0}>Clear</Button>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="source-panel-content">
        {sources.length === 0 ? (
          <Empty className="queue-empty">
            <EmptyHeader>
              <EmptyMedia variant="icon"><IconFile size={22} /></EmptyMedia>
              <EmptyTitle>Nothing in the queue yet.</EmptyTitle>
              <EmptyDescription>Add a document above. Its structure and extraction route will appear here.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <>
            <Input
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              placeholder="Find a source…"
              aria-label="Search source files"
              className="source-search"
            />
            <div className="source-scroll" role="region" aria-label="Source file queue" tabIndex={0}>
              <div className="source-list" aria-live="polite">
                {visibleSources.map((source) => {
                  const result = results.find((item) => item.filename === source.file.name)
                  const included = includedIds.includes(source.id)
                  const selected = source.id === activeId
                  return (
                    <div className={`source-row ${selected ? 'is-selected' : ''}`} key={source.id}>
                      <Button
                        variant="ghost"
                        className="source-select"
                        aria-pressed={selected}
                        onClick={() => onSelect(source.id)}
                      >
                        <span className="source-file-icon"><FileIcon filename={source.file.name} /></span>
                        <span className="source-file-copy">
                          <strong title={source.file.name}>{source.file.name}</strong>
                          <small>{fileExtension(source.file.name).toUpperCase()} <span>·</span> {formatBytes(source.file.size)}</small>
                          {source.status === 'error' && <small className="source-error-text">{source.error}</small>}
                        </span>
                      </Button>
                      <div className="source-row-actions">
                        {source.status === 'queued' && <Badge variant="outline">Queued</Badge>}
                        {source.status === 'processing' && <Badge variant="secondary">Reading</Badge>}
                        {source.status === 'success' && <Badge variant="secondary"><IconCheck data-icon="inline-start" size={13} /> Ready</Badge>}
                        {source.status === 'error' && <Badge variant="destructive"><IconAlertTriangle data-icon="inline-start" size={13} /> Error</Badge>}
                        {source.status === 'error' && <Button variant="ghost" size="icon-sm" title="Retry this source" aria-label={`Retry ${source.file.name}`} disabled={busy} onClick={() => onRetry(source)}><IconRefresh size={16} /></Button>}
                        {result?.status === 'success' && (
                          <Button
                            variant={included ? 'secondary' : 'outline'}
                            size="sm"
                            className="include-button"
                            aria-pressed={included}
                            onClick={() => onToggleInclude(source.id)}
                            disabled={busy}
                          >
                            {included ? 'In pack' : 'Add to pack'}
                          </Button>
                        )}
                        <Button variant="ghost" size="icon-sm" aria-label={`Remove ${source.file.name}`} disabled={busy} onClick={() => onRemove(source.id)}>
                          <IconX size={16} />
                        </Button>
                      </div>
                    </div>
                  )
                })}
                {visibleSources.length === 0 && <p className="no-search-results">No source names match “{search}”.</p>}
              </div>
            </div>
            <div className="source-controls">
              <div className="processing-policy">
                <label htmlFor="processing-mode">PROCESSING</label>
                <select id="processing-mode" className="native-select" value={mode} onChange={(event) => onModeChange(event.target.value as ProcessingMode)}>
                  <option value="auto">Automatic · OCR when available</option>
                  <option value="native_only">Native text only</option>
                </select>
              </div>
              <Button onClick={onBuild} disabled={!canBuild || busy}>
                {busy ? <><span className="button-spinner" /> Processing</> : 'Build context'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
