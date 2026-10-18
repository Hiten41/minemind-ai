'use client'

import { useEffect, useState } from 'react'
import { getDocumentFile } from '@/lib/api'
import type { Source } from '@/types'

export default function EvidenceSource({ source, open: controlledOpen, onOpenChange }: { source: Source; open?: boolean; onOpenChange?: (open: boolean) => void }) {
  const [localOpen, setLocalOpen] = useState(false)
  const open = controlledOpen ?? localOpen
  const setOpen = onOpenChange ?? setLocalOpen
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open || !source.document_id || source.available === false) return
    let cancelled = false
    let objectUrl = ''
    getDocumentFile(source.document_id).then((blob) => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(blob)
      setUrl(objectUrl)
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Source unavailable')
    })
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [open, source.document_id, source.available])
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
      <button type="button" className="min-h-11 w-full text-left text-sm text-white/80" aria-expanded={open} onClick={() => setOpen(!open)}>
        {source.title} {source.page ? `· Page ${source.page}` : ''} {source.section ? `· ${source.section}` : ''}
        <span className="block text-xs text-[#d7b779]">{open ? 'Close evidence' : 'Inspect evidence'}</span>
      </button>
      {open && <div className="mt-3 space-y-3">
        <blockquote className="whitespace-pre-wrap border-l-2 border-[#d7b779] pl-3 text-sm text-white/80">{source.excerpt}</blockquote>
        <p className="text-xs text-white/50">Exact cited passage</p>
        {source.available === false || !source.document_id ? <p role="status">Original source is unavailable. Historical chat text is retained.</p> : <>
          {error && <p role="alert">{error}</p>}
          {!url && !error && <p role="status">Loading source…</p>}
          {url && <a className="block text-[#d7b779] underline" href={url} download={source.title}>Download original</a>}
          {url && /\.pdf$/i.test(source.title) && <iframe title={`Evidence from ${source.title}`} src={`${url}#page=${source.page || 1}`} className="h-96 w-full rounded-xl bg-white" />}
        </>}
      </div>}
    </div>
  )
}
