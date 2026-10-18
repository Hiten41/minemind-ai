'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { BrainCircuit, Check, ChevronDown, FileSearch, Send, ShieldCheck, Sparkles, Wand2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import ChatWindow from '@/components/chat/ChatWindow'
import SourcePanel from '@/components/chat/SourcePanel'
import { useChatHistory } from '@/components/chat/useChatHistory'
import BackToDashboard from '@/components/experience/BackToDashboard'
import PremiumNav from '@/components/experience/PremiumNav'
import { getDocumentIntelligence, getDocuments, queryAI } from '@/lib/api'
import type { ChatMessage, Document, DocumentIntelligence, DocumentIntelligenceItem, Source } from '@/types'

type Suggestion = {
  icon: LucideIcon
  label: string
  prompt: string
}

const defaultSuggestions: Suggestion[] = [
  {
    icon: ShieldCheck,
    label: 'Safety Rules',
    prompt: 'Which regulations apply to roof support?'
  },
  {
    icon: FileSearch,
    label: 'Incident Recall',
    prompt: 'Show incidents involving hydraulic failure'
  },
  {
    icon: Wand2,
    label: 'Maintenance',
    prompt: 'What maintenance is overdue?'
  },
  {
    icon: BrainCircuit,
    label: 'PPE Guidance',
    prompt: 'What PPE is required for blasting?'
  }
]


function firstSignal(document: DocumentIntelligenceItem, intelligence: DocumentIntelligence): string {
  return (
    document.signals.hazards[0] ??
    document.signals.actions[0] ??
    document.signals.equipment[0] ??
    intelligence.top_entities[0]?.name ??
    'safety requirements'
  )
}

function buildDynamicSuggestions(intelligence: DocumentIntelligence): Suggestion[] {
  const [primaryDocument, secondaryDocument] = intelligence.documents
  if (!primaryDocument) return defaultSuggestions

  const topEntity = firstSignal(primaryDocument, intelligence)
  const hasIncidents = intelligence.documents.some(
    (document) =>
      document.type === 'incident' ||
      document.signals.hazards.some((hazard) => ['accident', 'fatal', 'death', 'injury'].includes(hazard))
  )

  return [
    {
      icon: FileSearch,
      label: 'Document Focus',
      prompt: `What does ${primaryDocument.name} say about ${topEntity}?`
    },
    {
      icon: ShieldCheck,
      label: 'Key Regulations',
      prompt: `What are the key regulations in ${secondaryDocument?.name ?? primaryDocument.name}?`
    },
    {
      icon: BrainCircuit,
      label: 'Safety Summary',
      prompt: 'Summarize the main safety requirements'
    },
    {
      icon: hasIncidents ? Wand2 : FileSearch,
      label: hasIncidents ? 'Incident Memory' : 'Memory Topics',
      prompt: hasIncidents ? 'What incidents are documented?' : `What are the main topics in ${primaryDocument.name}?`
    }
  ]
}

function ChatContent() {
  const searchParams = useSearchParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>(defaultSuggestions)
  const [documents, setDocuments] = useState<Document[]>([])
  const [documentsState, setDocumentsState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [scopeSelected, setScopeSelected] = useState(false)
  const [scopeOpen, setScopeOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const sentInitial = useRef(false)
  const hasInteracted = useRef(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const latestSources: Source[] = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    return latestAssistant?.sources ?? []
  }, [messages])

  const inputPlaceholder = 'Ask MineMind about your documents...'

  const selectedDocumentLabel = useMemo(() => {
    if (documentsState === 'loading') return 'Loading documents...'
    if (documentsState === 'error') return 'Documents unavailable — retry'
    if (documents.length === 0) return 'No documents uploaded'
    if (!scopeSelected) return 'Choose documents'
    if (selectedDocumentIds.length === 0) return 'All uploaded documents'
    if (selectedDocumentIds.length === 1) {
      return documents.find((document) => document.id === selectedDocumentIds[0])?.name ?? '1 selected document'
    }
    return `${selectedDocumentIds.length} selected documents`
  }, [documents, documentsState, scopeSelected, selectedDocumentIds])

  const loadDocuments = useCallback(async () => {
    setDocumentsState('loading')
    try {
      const items = (await getDocuments()).filter((doc) => !['deleted', 'delete_pending', 'delete_failed'].includes(doc.status))
      setDocuments(items)
      setSelectedDocumentIds((current) => current.filter((id) => items.some((document) => document.id === id)))
      setDocumentsState('ready')
    } catch {
      setDocuments([])
      setDocumentsState('error')
    }
  }, [])

  function chooseAllDocuments() {
    setSelectedDocumentIds([])
    setScopeSelected(true)
  }

  function toggleDocument(documentId: string) {
    if (selectedDocumentIds.includes(documentId)) {
      const remaining = selectedDocumentIds.filter((id) => id !== documentId)
      setSelectedDocumentIds(remaining)
      setScopeSelected(remaining.length > 0)
      return
    }
    setSelectedDocumentIds((current) => [...current, documentId])
    setScopeSelected(true)
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useChatHistory(hasInteracted, setMessages, setError)

  useEffect(() => {
    void loadDocuments()
  }, [loadDocuments])

  useEffect(() => {
    let cancelled = false

    getDocumentIntelligence()
      .then((intelligence) => {
        if (cancelled) return
        setSuggestions(
          intelligence.documents.length > 0
            ? buildDynamicSuggestions(intelligence)
            : defaultSuggestions
        )
      })
      .catch(() => {
        if (!cancelled) setSuggestions(defaultSuggestions)
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function sendQuestion(question: string) {
    const trimmed = question.trim()
    if (!trimmed || loading) return
    if (documentsState === 'loading') {
      setError('Your documents are still loading. Please wait a moment.')
      return
    }
    if (documentsState === 'error') {
      setError('Your documents could not be loaded. Retry loading them before asking a question.')
      return
    }
    if (documents.length > 0 && !scopeSelected) {
      setError('Choose which document(s) MineMind should use before sending your question.')
      setScopeOpen(true)
      return
    }

    hasInteracted.current = true
    const userMessage: ChatMessage = { role: 'user', content: trimmed }
    const nextMessages = [...messages, userMessage]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError('')

    try {
      const response = await queryAI(
        trimmed,
        messages.slice(-10).map((message) => ({ role: message.role, content: message.content })),
        selectedDocumentIds
      )
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.answer,
          content_parts: response.content_parts,
          reasoning: response.reasoning,
          sources: response.sources,
          related_memories: response.related_memories,
          evidence_status: response.evidence_status,
          effective_document_ids: response.effective_document_ids,
          retrieval_diagnostics: response.retrieval_diagnostics,
          query_type: response.query_type
        }
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const query = searchParams.get('q')
    if (query && !sentInitial.current) {
      sentInitial.current = true
      setInput(query)
      setScopeOpen(true)
      setError('Choose the document scope, then send your question.')
    }
  }, [searchParams])

  return (
    <main className="premium-bg noise-mask relative h-[100dvh] overflow-hidden text-white">
      <PremiumNav />
      <BackToDashboard />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_22%_24%,rgba(215,183,121,0.12),transparent_28%),radial-gradient(circle_at_84%_58%,rgba(96,119,139,0.16),transparent_30%)]" />
      <div className="pointer-events-none absolute left-1/2 top-24 h-px w-[78vw] -translate-x-1/2 bg-gradient-to-r from-transparent via-white/18 to-transparent" />

      <section className="relative z-10 mx-auto grid h-[100dvh] max-w-7xl grid-cols-1 gap-4 overflow-hidden px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-32 sm:px-5 sm:pb-[calc(1rem+env(safe-area-inset-bottom))] sm:pt-28 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-5 lg:px-6 lg:pb-6 lg:pt-24">
        <div className="glass-depth flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[24px] sm:rounded-[32px]">
          <header className="relative z-40 border-b border-white/10 px-4 py-3 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="tracked-label text-[10px] text-[#d7b779]/70">Ask MineMind</p>
                <h1 className="mt-2 text-xl font-semibold leading-tight text-white sm:text-3xl">Operational memory chat</h1>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-2 text-xs text-white/54">
                  Memory ready
                </span>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => {
                      if (documentsState === 'error') {
                        void loadDocuments()
                        return
                      }
                      setScopeOpen((open) => !open)
                    }}
                    disabled={documentsState === 'loading' || (documentsState === 'ready' && documents.length === 0)}
                    className="flex max-w-[min(100%,320px)] items-center gap-2 rounded-full border border-[#d7b779]/30 bg-[#d7b779]/[0.08] px-3 py-2 text-left text-xs text-[#f6d08a] transition hover:border-[#d7b779]/55 hover:text-white disabled:cursor-not-allowed disabled:opacity-55"
                    aria-expanded={scopeOpen}
                    aria-haspopup="listbox"
                  >
                    <FileSearch className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
                    <span className="truncate">{selectedDocumentLabel}</span>
                    <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition ${scopeOpen ? 'rotate-180' : ''}`} strokeWidth={1.8} />
                  </button>
                  <AnimatePresence>
                    {scopeOpen ? (
                      <motion.div
                        initial={{ opacity: 0, y: -6, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -6, scale: 0.98 }}
                        transition={{ duration: 0.16 }}
                        className="absolute right-0 top-[calc(100%+0.6rem)] z-50 w-[min(22rem,calc(100vw-2.5rem))] rounded-2xl border border-white/20 bg-[#202222] p-3 text-white shadow-[0_20px_60px_rgba(0,0,0,0.65)]"
                      >
                        {documentsState === 'loading' ? (
                          <div className="px-3 py-4 text-sm text-white/56">Loading your uploaded documents...</div>
                        ) : documentsState === 'error' ? (
                          <div className="px-3 py-3">
                            <p className="text-sm text-red-100">Your documents could not be loaded.</p>
                            <button
                              type="button"
                              onClick={() => void loadDocuments()}
                              className="mt-3 rounded-xl bg-white/[0.08] px-3 py-2 text-xs font-medium text-white/72 transition hover:bg-white/[0.12] hover:text-white"
                            >
                              Retry loading documents
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="px-3 pb-2 pt-1">
                              <p className="tracked-label text-[9px] text-[#d7b779]/72">Question scope</p>
                              <p className="mt-1 text-sm leading-5 text-white/80">Choose the documents MineMind should use for this question.</p>
                            </div>
                            <button
                              type="button"
                              role="option"
                              aria-selected={scopeSelected && selectedDocumentIds.length === 0}
                              onClick={chooseAllDocuments}
                              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                                scopeSelected && selectedDocumentIds.length === 0
                                  ? 'bg-[#d7b779]/15 text-white'
                                  : 'text-white/90 hover:bg-white/[0.08] hover:text-white'
                              }`}
                            >
                              <span className={`grid h-4 w-4 place-items-center rounded border ${scopeSelected && selectedDocumentIds.length === 0 ? 'border-[#d7b779] bg-[#d7b779] text-black' : 'border-white/25'}`}>
                                {scopeSelected && selectedDocumentIds.length === 0 ? <Check className="h-3 w-3" strokeWidth={2.4} /> : null}
                              </span>
                              All uploaded documents
                            </button>
                            <div className="my-1 h-px bg-white/10" />
                            <div className="max-h-56 overflow-auto pr-1" role="listbox" aria-label="Choose documents for this question">
                              {documents.map((document) => {
                                const selected = selectedDocumentIds.includes(document.id)
                                return (
                                  <button
                                    key={document.id}
                                    type="button"
                                    role="option"
                                    aria-selected={selected}
                                    aria-label={`Use ${document.name}, document ${document.id.slice(0, 8)}, for this question`}
                                    onClick={() => toggleDocument(document.id)}
                                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                                      selected
                                        ? 'bg-[#d7b779]/15 text-white'
                                        : 'text-white/90 hover:bg-white/[0.08] hover:text-white'
                                    }`}
                                  >
                                    <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${selected ? 'border-[#d7b779] bg-[#d7b779] text-black' : 'border-white/25'}`}>
                                      {selected ? <Check className="h-3 w-3" strokeWidth={2.4} /> : null}
                                    </span>
                                    <span className="min-w-0 flex-1 truncate">{document.name}</span>
                                    <span className="shrink-0 text-right text-[10px] uppercase tracking-[0.14em] text-white/70">
                                      <span className="block">{document.type}</span>
                                      <span className="mt-0.5 block normal-case tracking-normal text-white/60">#{document.id.slice(0, 8)}</span>
                                    </span>
                                  </button>
                                )
                              })}
                            </div>
                            <button
                              type="button"
                              onClick={() => setScopeOpen(false)}
                              className="mt-2 w-full rounded-xl bg-white/[0.08] px-3 py-2 text-xs font-medium text-white/72 transition hover:bg-white/[0.12] hover:text-white"
                            >
                              Done
                            </button>
                          </>
                        )}
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-auto px-4 py-4 sm:px-6 sm:py-6">
          {messages.length === 0 ? (
            <div className="grid min-h-full place-items-center">
              <div className="w-full max-w-4xl">
                <motion.div
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                  className="text-center"
                >
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-[24px] border border-[#d7b779]/20 bg-[#d7b779]/10 text-[#d7b779] shadow-[0_0_60px_rgba(215,183,121,0.16)]">
                    <Sparkles className="h-7 w-7" strokeWidth={1.5} />
                  </div>
                  <h2 className="mt-6 text-3xl font-semibold text-white sm:text-4xl">Ask from the mine memory.</h2>
                  <p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-white/48 sm:text-base sm:leading-7">
                    Query uploaded reports, regulations, maintenance notes, and recalled incident context from one focused command surface.
                  </p>
                </motion.div>

                <div className="mt-8 grid gap-3 md:grid-cols-2">
                  {suggestions.map((suggestion, index) => {
                    const Icon = suggestion.icon
                    return (
                      <motion.button
                        key={suggestion.prompt}
                        type="button"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.08 * index, duration: 0.45 }}
                        onClick={() => void sendQuestion(suggestion.prompt)}
                        className="group rounded-[22px] border border-white/10 bg-white/[0.045] p-4 text-left transition hover:border-[#d7b779]/35 hover:bg-white/[0.075] hover:shadow-[0_24px_90px_rgba(215,183,121,0.08)] sm:rounded-[24px] sm:p-5"
                      >
                        <div className="flex items-center gap-3">
                          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-white/[0.07] text-[#d7b779] transition group-hover:bg-[#d7b779] group-hover:text-black">
                            <Icon className="h-5 w-5" strokeWidth={1.55} />
                          </span>
                          <span className="text-sm font-semibold text-white/78">{suggestion.label}</span>
                        </div>
                        <p className="mt-4 text-sm leading-6 text-white/46">{suggestion.prompt}</p>
                      </motion.button>
                    )
                  })}
                </div>
              </div>
            </div>
          ) : (
            <ChatWindow messages={messages} />
          )}
          <AnimatePresence>
            {loading ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="mt-5 flex min-w-0"
              >
                <div className="glass-depth-subtle flex min-w-0 items-center gap-3 rounded-2xl px-4 py-3">
                  <span className="text-sm text-white/56">Reading memory</span>
                  <span className="flex gap-1">
                    {[0, 1, 2].map((dot) => (
                      <span
                        key={dot}
                        className="h-2 w-2 animate-pulse rounded-full bg-[#d7b779]"
                        style={{ animationDelay: `${dot * 120}ms` }}
                      />
                    ))}
                  </span>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
          {error ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              {error}
            </div>
          ) : null}
          <div ref={bottomRef} />
          </div>

          <div className="shrink-0 border-t border-white/10 bg-black/18 p-2 sm:p-3">
            {documentsState === 'error' ? (
              <button
                type="button"
                onClick={() => void loadDocuments()}
                className="mb-2 flex max-w-full items-center gap-2 px-2 text-left text-xs text-red-100 transition hover:text-white"
              >
                <FileSearch className="h-3.5 w-3.5 shrink-0" strokeWidth={1.7} />
                Documents could not be loaded. Retry
              </button>
            ) : documentsState === 'loading' ? (
              <p className="mb-2 px-2 text-xs text-white/42">Loading available documents...</p>
            ) : documents.length > 0 ? (
              <button
                type="button"
                onClick={() => setScopeOpen(true)}
                className="mb-2 flex max-w-full items-center gap-2 px-2 text-left text-xs text-white/48 transition hover:text-white/78"
              >
                <FileSearch className="h-3.5 w-3.5 shrink-0 text-[#d7b779]" strokeWidth={1.7} />
                <span className="shrink-0">Asking about:</span>
                <span className="truncate text-[#f6d08a]">{selectedDocumentLabel}</span>
                <span className="shrink-0 text-white/35">Change</span>
              </button>
            ) : null}
            <form
              className="glass-depth amber-aura flex items-center gap-2 rounded-[22px] p-2 sm:gap-3 sm:rounded-[28px]"
              onSubmit={(event) => {
                event.preventDefault()
                void sendQuestion(input)
              }}
            >
              <div className="hidden h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/[0.07] text-white/52 sm:grid">
                <BrainCircuit className="h-5 w-5" strokeWidth={1.55} />
              </div>
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={loading || documentsState !== 'ready'}
                placeholder={inputPlaceholder}
                title={inputPlaceholder}
                className="soft-focus-ring h-12 min-w-0 flex-1 bg-transparent px-2 text-sm text-white placeholder:text-white/34 disabled:opacity-60 sm:h-14 sm:px-1 sm:text-[15px]"
              />
              <button
                type="submit"
                disabled={loading || documentsState !== 'ready'}
                className="group grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[#d7b779] text-black shadow-[0_0_38px_rgba(215,183,121,0.28)] transition hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-55"
                aria-label="Send message"
              >
                <Send className="h-4 w-4 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" strokeWidth={1.8} />
              </button>
            </form>
          </div>
        </div>

        <div className="hidden min-h-0 lg:block">
          <SourcePanel sources={latestSources} />
        </div>
      </section>
    </main>
  )
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="premium-bg min-h-screen p-8 pt-24 text-white/48">Loading chat...</div>}>
      <ChatContent />
    </Suspense>
  )
}

