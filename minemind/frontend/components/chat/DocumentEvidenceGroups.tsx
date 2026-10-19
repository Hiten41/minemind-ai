'use client'

import { useState, type ReactNode } from 'react'
import type { Source } from '@/types'
import EvidenceSource from './EvidenceSource'

export default function DocumentEvidenceGroups({ sources, expanded, onExpandedChange, renderSource }: {
  sources: Source[]
  expanded?: string[]
  onExpandedChange?: (ids: string[]) => void
  renderSource?: (source: Source, index: number) => ReactNode
}) {
  const [localExpanded, setLocalExpanded] = useState<string[]>([])
  const open = expanded ?? localExpanded
  const setOpen = onExpandedChange ?? setLocalExpanded
  const groups = new Map<string, { source: Source; index: number }[]>()
  sources.forEach((source, index) => {
    const key = source.document_id
    groups.set(key, [...(groups.get(key) ?? []), { source, index }])
  })
  return <div className="space-y-2">{[...groups].map(([id, entries]) => {
    const isOpen = open.includes(id)
    return <section key={id}>
      <button type="button" aria-expanded={isOpen}
        onClick={() => setOpen(isOpen ? open.filter((key) => key !== id) : [...open, id])}
        className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-left text-xs text-[#d7b779]">
        {isOpen ? 'Hide evidence' : 'View evidence'} · {entries[0].source.title}
      </button>
      {isOpen && <div className="mt-2 space-y-2">{entries.map(({ source, index }) =>
        <div key={`${source.chunk_id}-${index}`}>{renderSource ? renderSource(source, index) : <EvidenceSource source={source} />}</div>
      )}</div>}
    </section>
  })}</div>
}
