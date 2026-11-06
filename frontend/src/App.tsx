import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTheme } from 'next-themes'
import {
  IconArrowUpRight,
  IconBook2,
  IconCheck,
  IconCircleDot,
  IconCloudUpload,
  IconCopy,
  IconDatabase,
  IconDownload,
  IconFileText,
  IconFingerprint,
  IconMoon,
  IconPencil,
  IconSearch,
  IconShieldCheck,
  IconSun,
  IconX,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import {
  editKnowledgeNode,
  getHealth,
  getKnowledgeNodes,
  getKnowledgeSources,
  getKnowledgeDigest,
  getKnowledgeVersions,
  ingestKnowledgeFiles,
  searchKnowledge,
} from '@/lib/api'
import { copyText, downloadMarkdown, fileExtension, formatBytes } from '@/lib/format'
import type { HealthStatus, KnowledgeDigest, KnowledgeNode, KnowledgeSearchResult, KnowledgeSource, ProcessingMode } from '@/lib/types'

type View = 'knowledge' | 'explore' | 'compile'
type Notice = { kind: 'success' | 'warning' | 'error'; message: string }

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function locatorLabel(locator: Record<string, string | number>) {
  const type = String(locator.type ?? 'document section').replaceAll('_', ' ')
  const details = Object.entries(locator)
    .filter(([key]) => !['type', 'markdown_start', 'markdown_end'].includes(key))
    .map(([key, value]) => `${key.replaceAll('_', ' ')} ${value}`)
  return details.length ? `${type} · ${details.join(' · ')}` : type
}

function makeContextPack(question: string, evidence: KnowledgeSearchResult[], digests: Record<string, KnowledgeDigest>, includeDigests: boolean) {
  const sources = [...new Map(evidence.map((item) => [item.source_id, item])).values()]
  const digestSections = includeDigests ? sources.flatMap((item) => {
    const digest = digests[item.source_id]
    if (!digest || digest.source_version_id !== item.source_version_id || !digest.text) return []
    const provenance = digest.evidence.map((reference, index) =>
      `- ${index + 1}. Node ${reference.node_id} · ${locatorLabel(reference.locator)} · characters ${reference.start_offset}–${reference.end_offset} · sentence SHA-256 ${reference.sentence_sha256}`,
    )
    return [[
      `## Cached document digest - ${item.display_name}`,
      `Source version: ${digest.version_number}`,
      `Digest method: ${digest.method} (extractive, deterministic)`,
      '',
      digest.text,
      '',
      '### Digest provenance',
      ...provenance,
    ].join('\n')]
  }) : []
  const digestSourceIds = new Set(sources.filter((item) => {
    const digest = digests[item.source_id]
    return includeDigests && digest?.source_version_id === item.source_version_id && Boolean(digest.text)
  }).map((item) => item.source_id))
  const remainingEvidence = evidence.filter((item) => !digestSourceIds.has(item.source_id))
  const sections = remainingEvidence.map((item, index) => [
    `## Evidence ${index + 1} — ${item.display_name}`,
    `Source version: ${item.version_number}`,
    `Location: ${locatorLabel(item.locator)}`,
    `Content hash: ${item.content_sha256}`,
    '',
    item.content,
  ].join('\n'))
  return [
    '# Context Studio — Compiled context',
    '',
    question.trim() ? `## Task\n\n${question.trim()}` : '## Task\n\nNo task question supplied.',
    '',
    ...(digestSections.length ? ['## Cached document digests', '', ...digestSections, ''] : []),
    ...(sections.length ? ['## Selected source evidence', '', ...sections, ''] : []),
    '---',
    'This pack contains source-backed passages, not generated conclusions. Verify cited evidence before relying on it.',
  ].join('\n')
}

function App() {
  const { theme, setTheme } = useTheme()
  const fileInput = useRef<HTMLInputElement>(null)
  const [view, setView] = useState<View>('knowledge')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [sources, setSources] = useState<KnowledgeSource[]>([])
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null)
  const [versions, setVersions] = useState<{ source_version_id: string; version_number: number; content_sha256: string; byte_size: number; file_extension: string; extraction_status: string; created_at: string }[]>([])
  const [activeDigest, setActiveDigest] = useState<KnowledgeDigest | null>(null)
  const [digests, setDigests] = useState<Record<string, KnowledgeDigest>>({})
  const [includeDigests, setIncludeDigests] = useState(false)
  const [nodes, setNodes] = useState<KnowledgeNode[]>([])
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [processingMode, setProcessingMode] = useState<ProcessingMode>('auto')
  const [sourceFilter, setSourceFilter] = useState('')
  const [query, setQuery] = useState('')
  const [searchedQuery, setSearchedQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([])
  const [selectedEvidence, setSelectedEvidence] = useState<Record<string, KnowledgeSearchResult>>({})
  const [compileQuestion, setCompileQuestion] = useState('')
  const [notice, setNotice] = useState<Notice | null>(null)

  const activeSource = sources.find((source) => source.id === activeSourceId) ?? null
  const activeNode = nodes.find((node) => node.id === activeNodeId) ?? nodes[0] ?? null
  const selectedItems = useMemo(() => Object.values(selectedEvidence), [selectedEvidence])
  const nodeDepths = useMemo(() => {
    const parents = new Map(nodes.map((node) => [node.id, node.parent_node_id]))
    return new Map(nodes.map((node) => {
      let depth = 0
      let parent = parents.get(node.id)
      const visited = new Set([node.id])
      while (parent && parents.has(parent) && !visited.has(parent)) {
        depth += 1
        visited.add(parent)
        parent = parents.get(parent)
      }
      return [node.id, depth] as const
    }))
  }, [nodes])
  const contextPack = useMemo(
    () => makeContextPack(compileQuestion, selectedItems, digests, includeDigests),
    [compileQuestion, selectedItems, digests, includeDigests],
  )
  const tokenEstimate = Math.ceil(contextPack.length / 4)
  const filteredSources = sources.filter((source) => source.display_name.toLowerCase().includes(sourceFilter.toLowerCase()))

  const notify = useCallback((kind: Notice['kind'], message: string) => {
    setNotice({ kind, message })
  }, [])

  const refreshSources = useCallback(async () => {
    const data = await getKnowledgeSources()
    setSources(data.sources)
    return data.sources
  }, [])

  useEffect(() => {
    let mounted = true
    Promise.all([getHealth(), getKnowledgeSources()])
      .then(([healthResult, sourceResult]) => {
        if (!mounted) return
        setHealth(healthResult)
        setSources(sourceResult.sources)
        if (sourceResult.sources.length) setActiveSourceId(sourceResult.sources[0].id)
      })
      .catch((error: unknown) => { if (mounted) notify('error', errorMessage(error)) })
    return () => { mounted = false }
  }, [notify])

  useEffect(() => {
    if (!activeSource?.source_version_id) return
    let mounted = true
    Promise.all([
      getKnowledgeNodes(activeSource.source_version_id),
      getKnowledgeVersions(activeSource.id),
    ])
      .then(([nodeResult, versionResult]) => {
        if (!mounted) return
        setNodes(nodeResult.nodes)
        setVersions(versionResult.versions)
        setActiveNodeId(nodeResult.nodes[0]?.id ?? null)
        setDraft(nodeResult.nodes[0]?.content ?? '')
        setEditing(false)
      })
      .catch((error: unknown) => { if (mounted) notify('error', errorMessage(error)) })
    getKnowledgeDigest(activeSource.id)
      .then(({ digest }) => { if (mounted) setActiveDigest(digest) })
      .catch(() => { if (mounted) setActiveDigest(null) })
    return () => { mounted = false }
  }, [activeSource?.id, activeSource?.source_version_id, notify])



  useEffect(() => {
    const sourceIds = [...new Set(selectedItems.map((item) => item.source_id))]
    if (!sourceIds.length) return
    let mounted = true
    Promise.all(sourceIds.map(async (sourceId) => {
      try { return [sourceId, (await getKnowledgeDigest(sourceId)).digest] as const }
      catch { return null }
    })).then((entries) => {
      if (!mounted) return
      setDigests((current) => ({ ...current, ...Object.fromEntries(entries.filter((entry): entry is readonly [string, KnowledgeDigest] => entry !== null)) }))
    })
    return () => { mounted = false }
  }, [selectedItems])

  async function uploadFiles(incoming: FileList | File[]) {
    const files = Array.from(incoming)
    if (!files.length || uploading) return
    setUploading(true)
    setNotice(null)
    try {
      const response = await ingestKnowledgeFiles(files, processingMode)
      const succeeded = response.results.filter((item) => item.status === 'success' && item.knowledge)
      const failed = response.results.filter((item) => item.status === 'error')
      const refreshed = await refreshSources()
      if (succeeded.length) {
        setSelectedEvidence({})
        setSearchResults([])
        setDigests({})
      }
      const firstSourceId = succeeded[0]?.knowledge?.source_id
      if (firstSourceId) {
        setActiveSourceId(firstSourceId)
        setView('knowledge')
      }
      if (failed.length) notify('warning', `${succeeded.length} saved · ${failed.length} need attention: ${failed[0].filename} — ${failed[0].error}`)
      else notify('success', `${succeeded.length} source${succeeded.length === 1 ? '' : 's'} saved to the knowledge workspace.`)
      if (!refreshed.length) setActiveSourceId(null)
    } catch (error) {
      notify('error', errorMessage(error))
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!query.trim() || searching) return
    setSearching(true)
    try {
      const response = await searchKnowledge(query.trim())
      setSearchResults(response.results)
      setSearchedQuery(response.query)
      if (!response.results.length) notify('warning', 'No exact-term matches. Try a shorter query or different wording.')
    } catch (error) {
      notify('error', errorMessage(error))
    } finally {
      setSearching(false)
    }
  }

  function toggleEvidence(item: KnowledgeSearchResult) {
    setSelectedEvidence((current) => {
      const next = { ...current }
      if (next[item.chunk_id]) delete next[item.chunk_id]
      else next[item.chunk_id] = item
      return next
    })
  }

  async function saveNode() {
    if (!activeNode || !activeSource?.source_version_id || saving || !draft.trim()) return
    setSaving(true)
    try {
      await editKnowledgeNode(activeNode.id, draft, 'Edited in the Context Studio knowledge workspace')
      const [updated, digestResult] = await Promise.all([
        getKnowledgeNodes(activeSource.source_version_id),
        getKnowledgeDigest(activeSource.id),
      ])
      setNodes(updated.nodes)
      setActiveDigest(digestResult.digest)
      setSelectedEvidence((current) => Object.fromEntries(Object.entries(current).filter(([, item]) => item.source_id !== activeSource.id)))
      setDigests((current) => ({ ...current, [activeSource.id]: digestResult.digest }))
      setDraft(updated.nodes.find((node) => node.id === activeNode.id)?.content ?? draft)
      setEditing(false)
      notify('success', 'Knowledge updated. Its search index has been refreshed; the original file is unchanged.')
      if (searchedQuery) {
        const search = await searchKnowledge(searchedQuery)
        setSearchResults(search.results)
      }
    } catch (error) {
      notify('error', errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  async function copyPack() {
    try {
      await copyText(contextPack)
      notify('success', 'Compiled context copied.')
    } catch (error) {
      notify('error', errorMessage(error))
    }
  }

  function exportPack() {
    downloadMarkdown(contextPack, 'context-studio-compiled-context.md')
    notify('success', 'Context pack exported.')
  }

  function selectNode(node: KnowledgeNode) {
    setActiveNodeId(node.id)
    setDraft(node.content)
    setEditing(false)
  }

  return (
    <div className="living-app">
      <header className="living-topbar">
        <a className="living-brand" href="/" aria-label="Context Studio home">
          <span className="living-brand-mark">C<span>.</span></span>
          <span>context studio</span>
        </a>
        <nav className="living-nav" aria-label="Workspace">
          {([
            ['knowledge', 'Knowledge', IconDatabase],
            ['explore', 'Explore', IconSearch],
            ['compile', 'Compile', IconArrowUpRight],
          ] as const).map(([key, label, Icon]) => (
            <button key={key} className={view === key ? 'is-active' : ''} onClick={() => setView(key)} aria-current={view === key ? 'page' : undefined}>
              <Icon size={16} stroke={1.7} /> {label}
              {key === 'compile' && selectedItems.length > 0 && <span className="living-nav-count">{selectedItems.length}</span>}
            </button>
          ))}
        </nav>
        <div className="living-top-actions">
          <span className="living-local-status"><i /> {health?.status === 'ok' ? 'Local workspace' : 'Connecting'}</span>
          <Button variant="ghost" size="icon" className="living-theme" aria-label="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
          </Button>
        </div>
      </header>

      <main className="living-main">
        <section className="living-hero">
          <div>
            <p className="living-kicker"><IconCircleDot size={13} /> A LIVING CONTEXT LAYER FOR AI</p>
            <h1>Keep knowledge current.<br /><em>Give AI the right context.</em></h1>
            <p className="living-subtitle">Your team's documents become versioned, searchable knowledge—with edits, evidence and history kept together.</p>
          </div>
          <div className="living-principles" aria-label="Product principles">
            <div><span>01</span><strong>Preserve</strong><small>Originals and versions</small></div>
            <div><span>02</span><strong>Understand</strong><small>Structure and retrieve</small></div>
            <div><span>03</span><strong>Deliver</strong><small>Evidence, not guesswork</small></div>
          </div>
        </section>

        {notice && (
          <div className={`living-notice is-${notice.kind}`} role="status">
            <span>{notice.kind === 'success' ? <IconCheck size={16} /> : <IconCircleDot size={16} />}{notice.message}</span>
            <button onClick={() => setNotice(null)} aria-label="Dismiss notice"><IconX size={15} /></button>
          </div>
        )}

        {view === 'knowledge' && (
          <section className="living-workspace">
            <div className="living-section-heading">
              <div><p className="living-kicker">01 / KNOWLEDGE</p><h2>Your source library</h2></div>
              <div className="living-heading-meta"><Badge variant="outline">{sources.length} sources</Badge><Badge variant="outline">{versions.length} versions selected</Badge></div>
            </div>

            <div
              className={`living-dropzone ${dragging ? 'is-dragging' : ''}`}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false) }}
              onDrop={(event) => { event.preventDefault(); setDragging(false); void uploadFiles(event.dataTransfer.files) }}
            >
              <input ref={fileInput} type="file" multiple className="visually-hidden" onChange={(event) => { if (event.target.files) void uploadFiles(event.target.files) }} aria-label="Choose documents to add to the knowledge library" />
              <span className="living-drop-icon"><IconCloudUpload size={23} stroke={1.5} /></span>
              <div><strong>{uploading ? 'Processing and saving sources…' : 'Add documents to your knowledge'}</strong><small>Drop files here or choose from your computer. New versions are detected by content hash.</small></div>
              <div className="living-drop-actions">
                <select value={processingMode} onChange={(event) => setProcessingMode(event.target.value as ProcessingMode)} aria-label="Document processing mode">
                  <option value="auto">Automatic extraction</option>
                  <option value="native_only">Native text only</option>
                </select>
                <Button onClick={() => fileInput.current?.click()} disabled={uploading}>{uploading ? 'Saving…' : 'Choose files'} <IconArrowUpRight size={15} /></Button>
              </div>
              <p className="living-drop-foot">PDF · DOCX · PPTX · XLSX · CSV · HTML · JSON · TXT · MD · PNG · JPG · WEBP</p>
            </div>

            <div className="living-knowledge-grid">
              <Card className="living-panel living-source-panel">
                <CardHeader className="living-panel-header">
                  <div><p className="living-kicker">LIBRARY</p><CardTitle>Sources</CardTitle></div>
                  <Badge variant="secondary">{sources.length}</Badge>
                </CardHeader>
                <CardContent className="living-panel-content">
                  <Input value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} placeholder="Filter sources…" aria-label="Filter source library" />
                  <div className="living-source-list">
                    {filteredSources.map((source) => (
                      <button key={source.id} className={`living-source-item ${source.id === activeSourceId ? 'is-selected' : ''}`} onClick={() => setActiveSourceId(source.id)}>
                        <span className="living-file-icon"><IconFileText size={18} /></span>
                        <span className="living-source-copy"><strong>{source.display_name}</strong><small>{fileExtension(source.display_name).toUpperCase()} · {formatBytes(source.byte_size ?? 0)} · v{source.version_number ?? 0}</small></span>
                        <Badge variant={source.extraction_status === 'complete' ? 'secondary' : 'outline'}>{source.extraction_status ?? 'new'}</Badge>
                      </button>
                    ))}
                    {!filteredSources.length && <div className="living-empty">{sources.length ? 'No source names match this filter.' : 'Your library is empty. Add a document to begin.'}</div>}
                  </div>
                  <div className="living-storage-note"><IconShieldCheck size={15} /> Original files stay on this device.</div>
                </CardContent>
              </Card>

              <Card className="living-panel living-document-panel">
                <CardHeader className="living-panel-header">
                  <div><p className="living-kicker">CANONICAL KNOWLEDGE</p><CardTitle>{activeSource?.display_name ?? 'Select a source'}</CardTitle></div>
                  {activeSource && <Badge variant="outline">Version {activeSource.version_number}</Badge>}
                </CardHeader>
                <CardContent className="living-panel-content">
                  {!activeSource ? (
                    <div className="living-empty living-document-empty"><IconBook2 size={28} /><strong>No document selected</strong><span>Add a source or select one from the library.</span></div>
                  ) : nodes.length === 0 ? (
                    <div className="living-empty">No extracted evidence blocks are available for this version.</div>
                  ) : (
                    <>
                      <div className="living-document-meta">
                        <span><IconFingerprint size={14} /> SHA-256 {activeSource.content_sha256?.slice(0, 18)}…</span>
                        <span>{nodes.length} evidence blocks</span>
                      </div>
                      {versions.length > 1 && (
                        <div className="living-version-strip">
                          <span>VERSION HISTORY</span>
                          {versions.map((version) => <Badge key={version.source_version_id} variant={version.source_version_id === activeSource.source_version_id ? 'secondary' : 'outline'}>v{version.version_number}</Badge>)}
                        </div>
                      )}
                      {activeDigest?.source_version_id === activeSource.source_version_id && activeDigest.text && (
                        <div className="living-digest">
                          <div><span>DOCUMENT DIGEST</span><Badge variant="outline">Cached / extractive</Badge></div>
                          <p>{activeDigest.text}</p>
                          <small>{activeDigest.summary_characters.toLocaleString()} / {activeDigest.input_characters.toLocaleString()} characters | {activeDigest.evidence.length} cited passages | no model call</small>
                        </div>
                      )}
                      <div className="living-node-tabs" aria-label="Document structure">
                        {nodes.map((node, index) => (
                          <button key={node.id} data-depth={Math.min(nodeDepths.get(node.id) ?? 0, 6)} data-node-type={node.node_type} className={node.id === activeNode?.id ? 'is-active' : ''} onClick={() => selectNode(node)}>
                            <span>{String(index + 1).padStart(2, '0')}</span>{locatorLabel(node.locator)}
                          </button>
                        ))}
                      </div>
                      {activeNode && (
                        <div className="living-editor">
                          <div className="living-editor-heading">
                            <div><strong>{locatorLabel(activeNode.locator)}</strong><small>{activeNode.origin === 'user_edited' ? 'User-corrected knowledge' : 'Extracted from original source'}</small></div>
                            {!editing ? (
                              <Button size="sm" variant="outline" onClick={() => { setDraft(activeNode.content); setEditing(true) }}><IconPencil size={14} /> Edit knowledge</Button>
                            ) : (
                              <div className="living-editor-actions"><Button size="sm" variant="ghost" onClick={() => { setDraft(activeNode.content); setEditing(false) }}>Cancel</Button><Button size="sm" onClick={() => void saveNode()} disabled={saving || !draft.trim()}>{saving ? 'Saving…' : 'Save correction'}</Button></div>
                            )}
                          </div>
                          {editing ? <textarea className="living-editor-textarea" value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Edit canonical knowledge text" /> : <pre className="living-node-content">{activeNode.content}</pre>}
                          <p className="living-immutable-note">Editing updates the working knowledge layer and search index. The uploaded original remains unchanged.</p>
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </section>
        )}

        {view === 'explore' && (
          <section className="living-workspace">
            <div className="living-section-heading">
              <div><p className="living-kicker">02 / EXPLORE</p><h2>Find the evidence</h2></div>
              <Badge variant="outline">Current source versions only</Badge>
            </div>
            <Card className="living-panel living-explore-panel">
              <CardContent className="living-panel-content">
                <form className="living-search-form" onSubmit={(event) => void runSearch(event)}>
                  <IconSearch size={20} />
                  <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search facts, names, decisions or phrases…" aria-label="Search the knowledge library" />
                  <Button type="submit" disabled={searching || !query.trim()}>{searching ? 'Searching…' : 'Search'} <IconArrowUpRight size={15} /></Button>
                </form>
                <div className="living-search-explainer">Lexical retrieval · SQLite FTS5 / BM25 · source-backed results. Semantic/vector retrieval and model-generated answers are not enabled yet.</div>
                {searchedQuery && <div className="living-results-heading"><strong>{searchResults.length} matches</strong><span>for “{searchedQuery}”</span></div>}
                <div className="living-results-list">
                  {searchResults.map((item) => {
                    const selected = Boolean(selectedEvidence[item.chunk_id])
                    return (
                      <article className="living-result" key={item.chunk_id}>
                        <div className="living-result-heading">
                          <div><strong>{item.display_name}</strong><Badge variant="outline">v{item.version_number}</Badge><Badge variant="secondary">{locatorLabel(item.locator)}</Badge></div>
                          <span>BM25 {item.rank_score.toFixed(3)}</span>
                        </div>
                        <p>{item.content}</p>
                        <div className="living-result-footer">
                          <span><IconFingerprint size={13} /> {item.content_sha256.slice(0, 16)}… · ~{item.token_estimate} tokens</span>
                          <Button size="sm" variant={selected ? 'secondary' : 'outline'} onClick={() => toggleEvidence(item)}>{selected ? <><IconCheck size={14} /> Added to context</> : 'Use this evidence'}</Button>
                        </div>
                      </article>
                    )
                  })}
                  {!searchResults.length && <div className="living-empty living-search-empty"><IconSearch size={27} /><strong>Search across your current knowledge</strong><span>Results include the original source, version and exact location.</span></div>}
                </div>
              </CardContent>
            </Card>
          </section>
        )}

        {view === 'compile' && (
          <section className="living-workspace">
            <div className="living-section-heading">
              <div><p className="living-kicker">03 / COMPILE</p><h2>Prepare context for an AI task</h2></div>
              <Badge variant="outline">{selectedItems.length} evidence items selected</Badge>
            </div>
            <div className="living-compile-grid">
              <Card className="living-panel">
                <CardHeader className="living-panel-header"><div><p className="living-kicker">TASK</p><CardTitle>What should the AI do?</CardTitle></div></CardHeader>
                <CardContent className="living-panel-content">
                  <textarea className="living-question" value={compileQuestion} onChange={(event) => setCompileQuestion(event.target.value)} placeholder="e.g. What is the current launch date, what changed, and which decision approved it?" aria-label="Context task or question" />
                  <Separator />
                  <div className="living-evidence-heading"><strong>Selected evidence</strong><span>{selectedItems.length} passages</span></div>
                  {selectedItems.map((item) => (
                    <div className="living-selected-item" key={item.chunk_id}>
                      <div><strong>{item.display_name}</strong><small>{locatorLabel(item.locator)} · v{item.version_number}</small><p>{item.content}</p></div>
                      <Button variant="ghost" size="icon-sm" aria-label={`Remove evidence from ${item.display_name}`} onClick={() => toggleEvidence(item)}><IconX size={15} /></Button>
                    </div>
                  ))}
                  {!selectedItems.length && <div className="living-empty">Go to Explore and add source passages to this context pack.</div>}
                  <div className="living-compile-actions"><Button variant="outline" onClick={() => setView('explore')}>Find more evidence <IconArrowUpRight size={14} /></Button><Button variant="ghost" onClick={() => setSelectedEvidence({})} disabled={!selectedItems.length}>Clear selection</Button></div>
                </CardContent>
              </Card>
              <Card className="living-panel living-output-card">
                  <CardHeader className="living-panel-header"><div><p className="living-kicker">COMPILED OUTPUT</p><CardTitle>Context brief</CardTitle></div><Badge variant="secondary">Provider-neutral</Badge></CardHeader>
                <CardContent className="living-panel-content">
                  <label className="living-digest-option"><input type="checkbox" checked={includeDigests} onChange={(event) => setIncludeDigests(event.target.checked)} /> Replace selected passages with the broader document digest <span>Uses the version-matched extractive digest and its evidence references. It can add more context—and more tokens—when it covers sections beyond your selected passages.</span></label>
                  <div className="living-output-metrics"><div><span>SELECTED</span><strong>{selectedItems.length}</strong></div><div><span>EST. TOKENS</span><strong>{tokenEstimate.toLocaleString()}</strong></div><div><span>CHARACTERS</span><strong>{contextPack.length.toLocaleString()}</strong></div></div>
                  <pre className="living-context-preview">{contextPack}</pre>
                  <div className="living-compile-actions"><Button onClick={() => void copyPack()} disabled={!selectedItems.length}><IconCopy size={15} /> Copy context</Button><Button variant="outline" onClick={exportPack} disabled={!selectedItems.length}><IconDownload size={15} /> Export .md</Button></div>
                  <p className="living-immutable-note">This is a cited evidence pack, not an AI-generated answer. The cached digests are deterministic extractive summaries with sentence-level provenance, not model-generated semantic summaries. No document is sent to an external model here.</p>
                </CardContent>
              </Card>
            </div>
          </section>
        )}

        <footer className="living-footer">
          <span><IconShieldCheck size={14} /> Local-first · Original sources preserved · No external model calls</span>
          <span>CONTEXT / COMPUTATION / COST</span>
        </footer>
      </main>
    </div>
  )
}

export default App


