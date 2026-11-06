import { IconAlertTriangle, IconCopy, IconDownload, IconFingerprint, IconRoute } from '@tabler/icons-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import type { ExtractionResult } from '@/lib/types'
import { formatBytes, markdownFilename } from '@/lib/format'

type Props = {
  result: ExtractionResult | null
  markdown: string
  editing: boolean
  packMarkdown: string
  packSourceCount: number
  packLimit: number
  onMarkdownChange: (value: string) => void
  onEdit: (value: boolean) => void
  onDownload: () => void
  onCopy: () => void
  onDownloadPack: () => void
  onCopyPack: () => void
}

export function ContextPreview({
  result, markdown, editing, packMarkdown, packSourceCount, packLimit,
  onMarkdownChange, onEdit, onDownload, onCopy, onDownloadPack, onCopyPack,
}: Props) {
  const route = result?.processing
  const evidence = result?.evidence
  const pageCount = result?.pages ?? 1
  const packPercent = packLimit ? Math.min(100, (packMarkdown.length / packLimit) * 100) : 0
  const packOverLimit = packMarkdown.length > packLimit

  return (
    <Card className="panel-card output-panel">
      <CardHeader className="panel-header">
        <div>
          <p className="eyebrow">02 / OUTPUT</p>
          <CardTitle>Context preview</CardTitle>
        </div>
        <Badge variant={result ? 'secondary' : 'outline'}>{result ? 'READY TO REVIEW' : 'WAITING FOR INPUT'}</Badge>
      </CardHeader>
      <Separator />

      {!result ? (
        <CardContent className="output-empty-wrap">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><IconRoute size={22} /></EmptyMedia>
              <EmptyTitle>Your output appears here.</EmptyTitle>
              <EmptyDescription>Build context to inspect the Markdown, extraction decision, source evidence and export size.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      ) : (
        <>
          <CardContent className="output-content">
            <div className="output-toolbar">
              <div className="output-file">
                <span className="output-file-icon"><IconFingerprint size={18} /></span>
                <div>
                  <strong>{markdownFilename(result.filename)}</strong>
                  <small>{result.format?.toUpperCase()} <span>·</span> {pageCount} page{pageCount === 1 ? '' : 's'}</small>
                </div>
              </div>
              <div className="output-actions">
                <Button variant={!editing ? 'secondary' : 'ghost'} size="sm" onClick={() => onEdit(false)}>Preview</Button>
                <Button variant={editing ? 'secondary' : 'ghost'} size="sm" onClick={() => onEdit(true)}>Edit</Button>
                <Button variant="outline" size="sm" onClick={onDownload}>
                  <IconDownload data-icon="inline-start" size={15} /> Export
                </Button>
              </div>
            </div>

            {editing ? (
              <textarea
                className="markdown-editor"
                value={markdown}
                onChange={(event) => onMarkdownChange(event.target.value)}
                aria-label="Edit extracted Markdown"
                spellCheck={false}
              />
            ) : (
              <div className="markdown-scroll" role="region" aria-label="Markdown preview" tabIndex={0}>
                <pre className="markdown-preview">{markdown}</pre>
              </div>
            )}

            <div className="output-metrics">
              <div><span>WORDS</span><strong>{(result.words ?? 0).toLocaleString()}</strong></div>
              <div><span>EST. TOKENS</span><strong>{(result.context?.estimated_tokens ?? 0).toLocaleString()}</strong></div>
              <div><span>LOCAL TIME</span><strong>{result.processing?.duration_ms ?? 0}<small> ms</small></strong></div>
              <div><span>EXTERNAL CALLS</span><strong>{result.processing?.external_model_calls ?? 0}</strong></div>
            </div>

            <div className="route-summary">
              <div className="route-summary-heading">
                <div>
                  <Badge variant="outline">{route?.route?.replaceAll('_', ' ') ?? 'deterministic parse'}</Badge>
                  {route?.mode && <Badge variant="outline">{route.mode}</Badge>}
                  <strong>{route?.route_label ?? 'Native document extraction'}</strong>
                </div>
                <span>{formatBytes(result.context?.input_bytes ?? 0)} <span>→</span> {formatBytes(result.context?.markdown_bytes ?? 0)}</span>
              </div>
              <p>{route?.decision?.reason ?? 'The file was parsed locally.'}</p>
              {!!route?.decision?.alternatives.length && (
                <ul className="route-alternatives">
                  {route.decision.alternatives.map((alternative) => (
                    <li key={`${alternative.route}-${alternative.status}`}><span>{alternative.route.replaceAll('_', ' ')}</span> · {alternative.status} · {alternative.reason}</li>
                  ))}
                </ul>
              )}
                <span className="evidence-id" title="SHA-256 of the original uploaded file">
                  <IconFingerprint size={14} /> Source {evidence?.source_id.slice(0, 16) ?? 'unavailable'}…
                </span>
              <span className="evidence-count">{evidence?.blocks.length ?? 0} evidence blocks</span>
            </div>

            {!!result.warnings?.length && (
              <Alert className="extraction-alert">
                <IconAlertTriangle />
                <AlertTitle>{result.warnings.length} extraction note{result.warnings.length === 1 ? '' : 's'}</AlertTitle>
                <AlertDescription>
                  <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
          <Separator />
          <CardFooter className="output-footer">
            <div className="footer-actions">
              <Button variant="ghost" size="sm" onClick={onCopy}><IconCopy data-icon="inline-start" size={15} /> Copy current file</Button>
              {editing && <Badge variant="outline">Edits stay in this session</Badge>}
            </div>
            <div className="pack-actions">
              <div className="pack-meter">
                <div><span>{packSourceCount} sources in pack</span><span>{packMarkdown.length.toLocaleString()} / {packLimit.toLocaleString()} chars</span></div>
                <progress className="pack-progress" value={packPercent} max={100} aria-label="Context pack character limit" />
              </div>
              <Button onClick={onDownloadPack} disabled={!packSourceCount || packOverLimit}>
                <IconDownload data-icon="inline-start" size={15} /> Export context pack
              </Button>
              <Button variant="ghost" size="icon" aria-label="Copy context pack" onClick={onCopyPack} disabled={!packSourceCount || packOverLimit}>
                <IconCopy size={16} />
              </Button>
            </div>
          </CardFooter>
          {packOverLimit && <div className="pack-limit-note"><IconAlertTriangle size={15} /> The selected pack is over the configured character limit. Remove a source or shorten its Markdown.</div>}
        </>
      )}
    </Card>
  )
}
