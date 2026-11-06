import { useState, type FormEvent } from 'react'
import { IconClipboard, IconEdit, IconPlus, IconTrash, IconX } from '@tabler/icons-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import type { ContextRule, ContextRuleDraft, ContextRuleList, RuleScope } from '@/lib/types'

type Props = {
  data: ContextRuleList | null
  loading: boolean
  maxRules: number
  onSave: (draft: ContextRuleDraft, id?: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onCopyEndpoint: () => void
}

const EMPTY_DRAFT: ContextRuleDraft = {
  title: '',
  scope: 'organization',
  project_key: null,
  tags: [],
  content: '',
  priority: 50,
  enabled: true,
}

function draftFromRule(rule: ContextRule): ContextRuleDraft {
  return {
    title: rule.title,
    scope: rule.scope,
    project_key: rule.project_key,
    tags: rule.tags,
    content: rule.content,
    priority: rule.priority,
    enabled: rule.enabled,
  }
}

export function ContextRulesPanel({ data, loading, maxRules, onSave, onDelete, onCopyEndpoint }: Props) {
  const [draft, setDraft] = useState<ContextRuleDraft>(EMPTY_DRAFT)
  const [editingId, setEditingId] = useState<string | undefined>()
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function resetForm() {
    setDraft(EMPTY_DRAFT)
    setEditingId(undefined)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    try {
      await onSave(draft, editingId)
      resetForm()
    } catch {
      // The parent reports the API error and keeps the draft available for correction.
    } finally {
      setSaving(false)
    }
  }

  function editRule(rule: ContextRule) {
    setDraft(draftFromRule(rule))
    setEditingId(rule.id)
  }

  async function toggleRule(rule: ContextRule) {
    try {
      await onSave({ ...draftFromRule(rule), enabled: !rule.enabled }, rule.id)
    } catch {
      // The parent reports the API error.
    }
  }

  return (
    <Card className="panel-card rules-panel">
      <CardHeader className="panel-header rules-header">
        <div>
          <p className="eyebrow">03 / PERSISTENT CONTEXT</p>
          <CardTitle>Context rules <Badge variant="secondary">{data?.rules.length ?? 0}</Badge></CardTitle>
          <p className="panel-description">Save the standards and instructions your local agents should receive for each project or task.</p>
        </div>
        <Button variant="outline" size="sm" onClick={onCopyEndpoint}>
          <IconClipboard data-icon="inline-start" size={15} /> Copy agent endpoint
        </Button>
      </CardHeader>
      <Separator />
      <CardContent className="rules-content">
        {data?.potential_overlaps.length ? (
          <Alert className="rules-overlap-alert">
            <AlertTitle>Review rules that share task tags</AlertTitle>
            <AlertDescription>
              {data.potential_overlaps.map((overlap) => (
                <p key={overlap.rule_ids.join(':')}>{overlap.titles.join(' / ')} share {overlap.shared_tags.join(', ')}. Review the guidance manually.</p>
              ))}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="rules-layout">
          <form className="rule-form" onSubmit={submit}>
            <div className="rule-form-heading">
              <h3>{editingId ? 'Edit rule' : 'Add a rule'}</h3>
              {editingId && <Button type="button" variant="ghost" size="sm" onClick={resetForm}><IconX data-icon="inline-start" size={14} /> Cancel</Button>}
            </div>
            <label className="field-label" htmlFor="rule-title">Rule title</label>
            <Input id="rule-title" value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} maxLength={120} required placeholder="e.g. Engineering standards" />

            <label className="field-label" htmlFor="rule-scope">Applies to</label>
            <select id="rule-scope" className="native-select" value={draft.scope} onChange={(event) => setDraft((current) => ({ ...current, scope: event.target.value as RuleScope }))}>
              <option value="organization">Organization</option>
              <option value="project">Project</option>
              <option value="task">Task</option>
            </select>

            {draft.scope !== 'organization' && <>
              <label className="field-label" htmlFor="rule-project">Project key</label>
              <Input id="rule-project" value={draft.project_key ?? ''} onChange={(event) => setDraft((current) => ({ ...current, project_key: event.target.value || null }))} maxLength={80} required placeholder="e.g. context-studio" />
            </>}

            {draft.scope === 'task' && <>
              <label className="field-label" htmlFor="rule-tags">Task tags</label>
              <Input id="rule-tags" value={draft.tags.join(', ')} onChange={(event) => setDraft((current) => ({ ...current, tags: event.target.value.split(',').map((tag) => tag.trim().toLowerCase()).filter(Boolean).slice(0, 20) }))} placeholder="release, accessibility, docs" />
            </>}

            <label className="field-label" htmlFor="rule-content">Guidance</label>
            <textarea id="rule-content" className="rule-textarea" value={draft.content} onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))} rows={5} maxLength={10000} required placeholder="Write clear instructions the agent should follow…" />

            <div className="rule-form-footer">
              <label className="priority-field" htmlFor="rule-priority"><span className="field-label">Priority</span><Input id="rule-priority" type="number" min={0} max={100} value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: Number(event.target.value) }))} /></label>
              <Button type="submit" disabled={saving}>{saving ? 'Saving…' : editingId ? 'Update rule' : <><IconPlus data-icon="inline-start" size={15} /> Save rule</>}</Button>
            </div>
          </form>

          <div className="rule-list-wrap">
            <div className="rule-list-heading"><h3>Saved guidance</h3><span>{data?.precedence.join(' → ') ?? 'organization → project → task'}</span></div>
            {loading ? (
              <div className="rule-skeletons"><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /></div>
            ) : data?.rules.length ? (
              <div className="rule-list">
                {data.rules.map((rule) => (
                  <article className={`rule-item ${rule.enabled ? '' : 'is-disabled'}`} key={rule.id}>
                    <div className="rule-item-main">
                      <div className="rule-item-title"><strong>{rule.title}</strong><Badge variant="outline">{rule.scope}</Badge></div>
                      <p>{rule.content}</p>
                      <small>{rule.project_key ?? 'All projects'}{rule.tags.length ? ` · ${rule.tags.join(', ')}` : ''} · Priority {rule.priority}</small>
                    </div>
                    <div className="rule-item-actions">
                      <Button variant="ghost" size="sm" onClick={() => void toggleRule(rule)}>{rule.enabled ? 'Disable' : 'Enable'}</Button>
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${rule.title}`} onClick={() => editRule(rule)}><IconEdit size={16} /></Button>
                      {confirmDeleteId === rule.id ? (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => setConfirmDeleteId(null)}>Cancel</Button>
                          <Button variant="destructive" size="sm" onClick={() => {
                            void onDelete(rule.id)
                            setConfirmDeleteId(null)
                          }}>Delete</Button>
                        </>
                      ) : (
                        <Button variant="ghost" size="icon-sm" aria-label={`Delete ${rule.title}`} onClick={() => setConfirmDeleteId(rule.id)}><IconTrash size={16} /></Button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty className="rules-empty">
                <EmptyHeader>
                  <EmptyMedia variant="icon"><IconClipboard size={20} /></EmptyMedia>
                  <EmptyTitle>No saved guidance yet.</EmptyTitle>
                  <EmptyDescription>Add organization, project or task rules. Agents can request only the rules that match their context.</EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </div>
        </div>
      </CardContent>
      <CardFooter className="rules-footer">
        <span>Organization → project → task. Higher priority applies first within each scope.</span>
        <span>{data?.rules.length ?? 0} / {maxRules} rules</span>
      </CardFooter>
    </Card>
  )
}
