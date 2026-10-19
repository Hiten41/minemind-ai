'use client'

import { Bot, ChevronDown, UserRound } from 'lucide-react'
import { useId, useRef, useState } from 'react'

import type { ChatMessage, ContentPart } from '@/types'
import EvidenceSource from './EvidenceSource'
import DocumentEvidenceGroups from './DocumentEvidenceGroups'

function evidenceTitle(title: string, index: number) {
  const cleanTitle = title.trim()
  if (!cleanTitle || cleanTitle.toLowerCase() === 'graph') {
    return `Memory evidence ${index + 1}`
  }
  return cleanTitle
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [showReasoning, setShowReasoning] = useState(false)
  const [openSources, setOpenSources] = useState<number[]>([])
  const [openDocuments, setOpenDocuments] = useState<string[]>([])
  const sourceNodes = useRef(new Map<number, HTMLDivElement>())
  const evidenceId = useId()
  const sources = message.sources || []
  const multipleDocuments = new Set(sources.map((source) => source.document_id)).size > 1

  function openEvidence(indexes: number[]) {
    setOpenDocuments((current) => [...new Set([...current, ...indexes.map((index) => sources[index].document_id)])])
    setOpenSources((current) => [...new Set([...current, ...indexes])])
    requestAnimationFrame(() => {
      const element = sourceNodes.current.get(indexes[0])
      element?.focus({ preventScroll: true })
      element?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    })
  }

  function citedContent(text: string, contentParts?: ContentPart[]) {
    // New responses carry readable text plus explicit citation links. Keep the
    // legacy parser for in-memory answers received before the API upgrade.
    const parts = contentParts?.length && contentParts.map((part) => part.text).join('') === text
      ? contentParts
      : text.split(/((?:\[SRC_\d+\][ \t]*)+)/g).map((part) => ({
        text: part,
        source_ids: /^(?:\[SRC_\d+\][ \t]*)+$/.test(part)
          ? [...part.matchAll(/\[(SRC_\d+)\]/g)].map((match) => match[1]) : []
      }))
    return parts.map((part, partIndex) => {
      if (!part.source_ids.length) return part.text
      const groups = new Map<string, number[]>()
      let unavailable = false
      for (const sourceId of part.source_ids) {
        const index = sources.findIndex((source) => source.source_id === sourceId)
        if (index < 0) { unavailable = true; continue }
        const source = sources[index]
        const key = `${source.document_id}:${source.page ?? source.section ?? source.chunk_id}`
        groups.set(key, [...new Set([...(groups.get(key) || []), index])])
      }
      return <span key={partIndex} className="inline-flex flex-wrap items-baseline gap-1 align-baseline whitespace-normal">
        {[...groups.entries()].map(([key, indexes]) => {
          const source = sources[indexes[0]]
          const location = source.page ? `pg. ${source.page}` : source.section || 'Source'
          const label = multipleDocuments ? `${source.title} · ${location}` : location
          return <button key={key} type="button" title={`${source.title}${source.page ? ` · Page ${source.page}` : ''} — view supporting passage`}
            aria-label={`View source: ${source.title}${source.page ? `, page ${source.page}` : source.section ? `, ${source.section}` : ''}`}
            aria-controls={indexes.map((index) => `${evidenceId}-${index}`).join(' ')}
            onClick={() => openEvidence(indexes)}
            className="inline-block max-w-full rounded px-1 text-xs leading-5 text-[#d7b779] underline decoration-[#d7b779]/40 underline-offset-2 hover:decoration-[#d7b779] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#d7b779]">
            {label}
          </button>
        })}
        {unavailable && <span className="text-xs text-white/50">Source unavailable</span>}
      </span>
    })
  }

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[94%] items-start gap-2 sm:max-w-[82%] sm:gap-3">
          <div className="min-w-0 break-words rounded-[20px] bg-[#d7b779] px-4 py-3 text-sm leading-6 text-black shadow-[0_18px_70px_rgba(215,183,121,0.16)] sm:rounded-[22px] sm:px-5">
            {message.content}
          </div>
          <div className="hidden h-10 w-10 shrink-0 place-items-center rounded-2xl border border-white/10 bg-white/[0.06] text-white/62 sm:grid">
            <UserRound className="h-4 w-4" strokeWidth={1.5} />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex max-w-full items-start gap-2 sm:max-w-[92%] sm:gap-3">
      <div className="hidden h-10 w-10 shrink-0 place-items-center rounded-2xl border border-[#d7b779]/20 bg-[#d7b779]/10 text-[#d7b779] sm:grid">
        <Bot className="h-4 w-4" strokeWidth={1.5} />
      </div>
      <div className="min-w-0 rounded-[22px] border border-white/10 bg-white/[0.055] px-4 py-4 text-white shadow-[0_24px_80px_rgba(0,0,0,0.24)] backdrop-blur-xl sm:rounded-[26px] sm:px-5">
      {message.evidence_status && <p className="mb-2 text-xs text-[#d7b779]">Evidence: {message.evidence_status.replaceAll('_', ' ')}</p>}
      {message.effective_document_ids && <p className="mb-2 text-xs text-white/50">Effective scope: {message.effective_document_ids.length} document(s)</p>}
      {message.retrieval_diagnostics?.semantic === 'unavailable' && <p role="status" className="mb-2 text-xs text-amber-200">Semantic retrieval unavailable; using local document search.</p>}
      <p className="whitespace-pre-wrap break-words text-sm leading-7 text-white/82">{citedContent(message.content, message.content_parts)}</p>
      {message.reasoning ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {message.reasoning ? (
            <button
              type="button"
              onClick={() => setShowReasoning((value) => !value)}
              className="flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs font-medium text-[#d7b779] transition hover:border-[#d7b779]/30"
            >
              {showReasoning ? 'Hide Reasoning' : 'Show Reasoning'}
              <ChevronDown className={`h-3.5 w-3.5 transition ${showReasoning ? 'rotate-180' : ''}`} strokeWidth={1.7} />
            </button>
          ) : null}
        </div>
      ) : null}
      {message.reasoning && showReasoning ? (
        <div className="mt-3 rounded-2xl border border-white/10 bg-black/24 p-4 text-sm leading-6 text-white/62">
          {citedContent(message.reasoning)}
        </div>
      ) : null}
      {message.sources && message.sources.length > 0 ? (
        <div className="mt-4 space-y-2">
          <DocumentEvidenceGroups sources={sources} expanded={openDocuments} onExpandedChange={setOpenDocuments}
            renderSource={(source, index) => <div id={`${evidenceId}-${index}`} tabIndex={-1}
            ref={(element) => { if (element) sourceNodes.current.set(index, element); else sourceNodes.current.delete(index) }}>
            <EvidenceSource source={source} open={openSources.includes(index)} onOpenChange={(open) => setOpenSources((current) => open ? [...new Set([...current, index])] : current.filter((item) => item !== index))} />
          </div>} />
        </div>
      ) : null}
      {message.related_memories && message.related_memories.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.related_memories.map((memory, index) => (
            <span key={`${memory.title}-${memory.summary}-${index}`} className="max-w-full break-words rounded-full border border-white/10 bg-white/[0.055] px-3 py-1 text-xs text-white/56">
              {evidenceTitle(memory.title, index)}
            </span>
          ))}
        </div>
      ) : null}
      </div>
    </div>
  )
}
