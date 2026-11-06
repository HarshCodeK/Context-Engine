import { useMemo, useState } from 'react'
import { IconSearch, IconTable } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { KnowledgeNode } from '@/lib/types'

type Props = {
  nodes: KnowledgeNode[]
  activeNodeId: string | null
  onSelect: (node: KnowledgeNode) => void
}

export function NativeTablePreview({ nodes, activeNodeId, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [visibleCount, setVisibleCount] = useState(10)
  const table = nodes.find((node) => node.node_type === 'table' && node.locator.type === 'csv_table')

  const records = useMemo(() => {
    if (!table) return []
    const rows = nodes.filter((node) => node.node_type === 'row' && node.parent_node_id === table.id)
    const cellsByRow = new Map<string, KnowledgeNode[]>()
    nodes.filter((node) => node.node_type === 'cell').forEach((cell) => {
      if (!cell.parent_node_id) return
      const cells = cellsByRow.get(cell.parent_node_id) ?? []
      cells.push(cell)
      cellsByRow.set(cell.parent_node_id, cells)
    })
    return rows.map((row) => ({
      row,
      cells: (cellsByRow.get(row.id) ?? []).sort(
        (a, b) => Number(a.locator.column) - Number(b.locator.column),
      ),
    }))
  }, [nodes, table])

  const columns = nodes
    .filter((node) => node.node_type === 'column' && node.parent_node_id === table?.id)
    .sort((a, b) => Number(a.locator.column) - Number(b.locator.column))
  const cellIndexCapped = table?.locator.cells_truncated === true
  const filtered = records.filter(({ row, cells }) => {
    const needle = query.trim().toLocaleLowerCase()
    if (!needle) return true
    return row.content.toLocaleLowerCase().includes(needle)
      || cells.some((cell) => cell.content.toLocaleLowerCase().includes(needle) || String(cell.title ?? '').toLocaleLowerCase().includes(needle))
  })
  const visible = filtered.slice(0, visibleCount)

  if (!table) return null

  return (
    <section className="native-table-explorer" aria-label="Native CSV table explorer">
      <div className="native-table-heading">
        <div>
          <p className="living-kicker">STRUCTURED DATA</p>
          <h3><IconTable size={17} /> Table explorer</h3>
          <p>Cells retain their original record, column and header. Select a value to inspect its provenance.</p>
        </div>
        <div className="native-table-badges">
          <Badge variant="outline">{records.length.toLocaleString()} records · {columns.length} columns</Badge>
          {cellIndexCapped && <Badge variant="outline">Index capped · {Number(table?.locator.indexed_cell_count ?? 0).toLocaleString()} cells</Badge>}
        </div>
      </div>
      {cellIndexCapped && <p className="native-table-cap-note">Some cells remain available in the extracted Markdown and original file but are not individually indexed. Search and cell-level selection cover the indexed portion.</p>}
      <div className="native-table-tools">
        <label className="native-table-search">
          <IconSearch size={16} />
          <Input value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(10) }} placeholder="Filter rows or cell values…" aria-label="Filter table rows and values" />
        </label>
        <span>{filtered.length.toLocaleString()} matching records</span>
      </div>
      <div className="native-table-scroll" role="region" aria-label="CSV data table" tabIndex={0}>
        <table className="native-table-grid">
          <thead>
            <tr>
              <th scope="col">Record</th>
              {columns.map((column) => <th scope="col" key={String(column.locator.column)}>{column.title || column.locator.header_label || `Column ${column.locator.column}`}</th>)}
            </tr>
          </thead>
          <tbody>
            {visible.map(({ row, cells }) => (
              <tr key={row.id}>
                <th scope="row">{row.locator.row}</th>
                {columns.map((column) => {
                  const cell = cells.find((item) => item.locator.column === column.locator.column)
                  if (!cell) return <td key={String(column.locator.column)}><span className="native-cell-empty">Not indexed</span></td>
                  const selected = cell.id === activeNodeId
                  return (
                    <td key={cell.id}>
                      <button
                        type="button"
                        className={`native-cell-button ${selected ? 'is-selected' : ''} ${cell.content === '' ? 'is-empty' : ''}`}
                        title={cell.content || 'Empty cell'}
                        aria-label={`${cell.title}, record ${row.locator.row}: ${cell.content || 'empty cell'}`}
                        aria-pressed={selected}
                        onClick={() => onSelect(cell)}
                      >
                        {cell.content || <span className="native-cell-empty">—</span>}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
            {!visible.length && <tr><td colSpan={columns.length + 1} className="native-table-no-results">No records match “{query}”.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="native-table-footer">
        <span>Original CSV bytes remain immutable · Values are not type-coerced</span>
        {visibleCount < filtered.length && <Button variant="outline" size="sm" onClick={() => setVisibleCount((count) => count + 10)}>Show 10 more</Button>}
      </div>
    </section>
  )
}
