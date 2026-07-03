'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { BrainCircuit, FileSearch, Send, ShieldCheck, Sparkles, Wand2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'

import ChatWindow from '@/components/chat/ChatWindow'
import SourcePanel from '@/components/chat/SourcePanel'
import BackToDashboard from '@/components/experience/BackToDashboard'
import PremiumNav from '@/components/experience/PremiumNav'
import { getChatHistory, getDocumentIntelligence, queryAI } from '@/lib/api'
import type { ChatMessage, DocumentIntelligence, DocumentIntelligenceItem, Source } from '@/types'

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

const temporalInputKeywords = ['before', 'after', 'between', 'since']

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

  const latestConfidence = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    return typeof latestAssistant?.confidence === 'number'
      ? Math.round(latestAssistant.confidence * 100)
      : null
  }, [messages])

  const inputPlaceholder = useMemo(() => {
    const lowered = input.toLowerCase()
    const hasTemporalHint = temporalInputKeywords.some((keyword) => lowered.includes(keyword))
    return hasTemporalHint
      ? 'Temporal query detected - searching memory timeline...'
      : 'Ask about regulations, manuals, incidents, or maintenance...'
  }, [input])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    getChatHistory()
      .then((history) => {
        if (!hasInteracted.current) setMessages(history)
      })
      .catch(() => setMessages([]))
  }, [])

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
        messages.slice(-10).map((message) => ({ role: message.role, content: message.content }))
      )
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.answer,
          reasoning: response.reasoning,
          sources: response.sources,
          related_memories: response.related_memories,
          confidence: response.confidence,
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
      void sendQuestion(query)
    }
  })

  return (
    <main className="premium-bg noise-mask relative h-[100dvh] overflow-hidden text-white">
      <PremiumNav />
      <BackToDashboard />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_22%_24%,rgba(215,183,121,0.12),transparent_28%),radial-gradient(circle_at_84%_58%,rgba(96,119,139,0.16),transparent_30%)]" />
      <div className="pointer-events-none absolute left-1/2 top-24 h-px w-[78vw] -translate-x-1/2 bg-gradient-to-r from-transparent via-white/18 to-transparent" />

      <section className="relative z-10 mx-auto grid h-[100dvh] max-w-7xl grid-cols-1 gap-4 overflow-hidden px-3 pb-3 pt-20 sm:px-5 sm:pb-4 sm:pt-24 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-5 lg:px-6 lg:pb-6">
        <div className="glass-depth flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[24px] sm:rounded-[32px]">
          <header className="border-b border-white/10 px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="tracked-label text-[10px] text-[#d7b779]/70">Ask MineMind</p>
                <h1 className="mt-2 text-2xl font-semibold text-white sm:text-3xl">Operational memory chat</h1>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-2 text-xs text-white/54">
                  Groq LLM
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-2 text-xs text-white/54">
                  Ollama embeddings
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-2 text-xs text-white/54">
                  {latestConfidence === null ? 'Memory ready' : `${latestConfidence}% confidence`}
                </span>
              </div>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-auto px-4 py-5 sm:px-6 sm:py-6">
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
                className="mt-5 flex"
              >
                <div className="glass-depth-subtle flex items-center gap-3 rounded-2xl px-4 py-3">
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
                disabled={loading}
                placeholder={inputPlaceholder}
                title={inputPlaceholder}
                className="soft-focus-ring h-12 min-w-0 flex-1 bg-transparent px-2 text-sm text-white placeholder:text-white/34 disabled:opacity-60 sm:h-14 sm:px-1 sm:text-[15px]"
              />
              <button
                type="submit"
                disabled={loading}
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

