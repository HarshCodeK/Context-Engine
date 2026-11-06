import type {
  ContextRuleDraft,
  ContextRuleList,
  ExtractionResult,
  HealthStatus,
  ProcessingMode,
  UploadConfig,
  KnowledgeSource,
  KnowledgeNode,
  KnowledgeSearchResult,
  KnowledgeIngestResult,
  KnowledgeDigest,
} from './types'

async function readResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = payload.error || payload.detail || `Request failed (${response.status})`
    throw new Error(message)
  }
  return payload as T
}

export async function getConfig() {
  return readResponse<UploadConfig>(await fetch('/api/config'))
}

export async function getHealth() {
  return readResponse<HealthStatus>(await fetch('/api/health'))
}

export async function extractFiles(files: File[], mode: ProcessingMode) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('processing_mode', mode)

  const response = await fetch('/api/extract', {
    method: 'POST',
    body: form,
    credentials: 'same-origin',
  })
  return readResponse<{ results: ExtractionResult[]; processed: number; storage: string }>(response)
}

export async function getContextRules() {
  return readResponse<ContextRuleList>(await fetch('/api/context-rules'))
}

export async function saveContextRule(draft: ContextRuleDraft, id?: string) {
  const response = await fetch(id ? `/api/context-rules/${id}` : '/api/context-rules', {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(draft),
  })
  return readResponse<{ rule: ContextRuleList['rules'][number] }>(response)
}

export async function deleteContextRule(id: string) {
  return readResponse<{ deleted: boolean; id: string }>(await fetch(`/api/context-rules/${id}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  }))
}


export async function ingestKnowledgeFiles(files: File[], mode: ProcessingMode) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('processing_mode', mode)
  form.append('workspace_id', 'default')
  return readResponse<{ results: KnowledgeIngestResult[]; processed: number; storage: string; workspace_id: string }>(
    await fetch('/api/knowledge/ingest', { method: 'POST', body: form, credentials: 'same-origin' }),
  )
}

export async function getKnowledgeSources() {
  return readResponse<{ sources: KnowledgeSource[] }>(await fetch('/api/knowledge/sources'))
}

export async function getKnowledgeNodes(sourceVersionId: string) {
  return readResponse<{ nodes: KnowledgeNode[] }>(await fetch(`/api/knowledge/versions/${encodeURIComponent(sourceVersionId)}/nodes`))
}

export async function getKnowledgeVersions(sourceId: string) {
  return readResponse<{ versions: { source_version_id: string; version_number: number; content_sha256: string; byte_size: number; file_extension: string; extraction_status: string; created_at: string }[] }>(
    await fetch(`/api/knowledge/sources/${encodeURIComponent(sourceId)}/versions`),
  )
}

export async function searchKnowledge(query: string, limit = 12) {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  return readResponse<{ query: string; results: KnowledgeSearchResult[]; count: number; ranking: string }>(
    await fetch(`/api/knowledge/search?${params.toString()}`),
  )
}

export async function editKnowledgeNode(nodeId: string, content: string, reason?: string) {
  return readResponse<{ edit: { edit_id: string; node_id: string; content_sha256: string } }>(
    await fetch(`/api/knowledge/nodes/${encodeURIComponent(nodeId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ content, reason }),
    }),
  )
}


export async function getKnowledgeDigest(sourceId: string) {
  return readResponse<{ digest: KnowledgeDigest }>(
    await fetch(`/api/knowledge/sources/${encodeURIComponent(sourceId)}/digest`),
  )
}
