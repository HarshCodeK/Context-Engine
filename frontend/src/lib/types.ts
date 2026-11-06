export type ProcessingMode = 'auto' | 'native_only'

export type UploadConfig = {
  max_files: number
  max_file_bytes: number
  max_batch_bytes: number
  max_context_pack_chars: number
  max_context_rules: number
  supported_extensions: string[]
}

export type HealthStatus = {
  status: string
  version: string
  ocr_available: boolean
}

export type EvidenceBlock = {
  block_id: string
  source_id: string
  locator: Record<string, string | number | boolean>
  markdown_range: { start: number; end: number; unit: string; end_exclusive: boolean }
  content_sha256: string
  extraction_method: string
}

export type NativeTableEvidence = {
  table_key: string
  title: string
  locator: Record<string, string | number | boolean>
  headers: { value: string; label: string; column_index: number; column_label: string }[]
  rows: {
    row_number: number
    values: string[]
    cells: {
      column_index: number
      column_label: string
      header: string
      header_label: string
      value: string
      is_empty: boolean
    }[]
  }[]
  indexed_cell_count: number
  cells_truncated: boolean
}

export type ExtractionEvidence = {
  schema_version: string
  source_id: string
  source_sha256: string
  blocks: EvidenceBlock[]
  tables?: NativeTableEvidence[]
}

export type ExtractionResult = {
  status: 'success' | 'error'
  filename: string
  markdown?: string
  words?: number
  characters?: number
  pages?: number
  warnings?: string[]
  format?: string
  processing?: {
    route: string
    route_label: string
    mode: string
    duration_ms: number
    external_model_calls: number
    decision: {
      policy: ProcessingMode
      selected_route: string
      reason: string
      alternatives: { route: string; status: string; reason: string }[]
    }
  }
  context?: { estimated_tokens: number; input_bytes: number; markdown_bytes: number }
  evidence?: ExtractionEvidence
  error?: string
}

export type QueuedSource = {
  id: string
  file: File
  status: 'queued' | 'processing' | 'success' | 'error'
  error?: string
}

export type RuleScope = 'organization' | 'project' | 'task'

export type ContextRule = {
  id: string
  title: string
  scope: RuleScope
  project_key: string | null
  tags: string[]
  content: string
  priority: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export type ContextRuleDraft = {
  title: string
  scope: RuleScope
  project_key: string | null
  tags: string[]
  content: string
  priority: number
  enabled: boolean
}

export type ContextRuleList = {
  rules: ContextRule[]
  potential_overlaps: {
    rule_ids: string[]
    titles: string[]
    scopes: string[]
    shared_tags: string[]
    message: string
  }[]
  precedence: string[]
}


export type KnowledgeSource = {
  id: string
  display_name: string
  created_at: string
  updated_at: string
  source_version_id: string | null
  version_number: number | null
  content_sha256: string | null
  byte_size: number | null
  extraction_status: 'pending' | 'complete' | 'partial' | 'failed' | null
}

export type KnowledgeNode = {
  id: string
  parent_node_id: string | null
  node_key: string
  ordinal: number
  node_type: string
  title: string | null
  content: string
  content_sha256: string
  origin: 'extracted' | 'user_edited' | 'model_derived'
  locator: Record<string, string | number | boolean>
}

export type KnowledgeSearchResult = {
  chunk_id: string
  source_version_id: string
  document_node_id: string
  source_id: string
  display_name: string
  version_number: number
  ordinal: number
  title: string
  content: string
  content_sha256: string
  token_estimate: number
  rank_score: number
  locator: Record<string, string | number | boolean>
}

export type KnowledgeIngestResult = {
  status: 'success' | 'error'
  filename: string
  error?: string
  evidence?: ExtractionEvidence
  knowledge?: {
    source_id: string
    source_version_id: string
    version_number: number
    content_sha256: string
    node_count: number
    chunk_count: number | null
    created_new_version: boolean
  }
}


export type KnowledgeDigest = {
  text: string
  method: string
  evidence: { node_id: string; locator: Record<string, string | number | boolean>; start_offset: number; end_offset: number; node_content_sha256: string; sentence_sha256: string; score: number }[]
  input_characters: number
  summary_characters: number
  source_version_id: string
  version_number: number
  content_sha256: string
  updated_at: string
}
