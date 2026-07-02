'use client'

import { Bot, ChevronDown, UserRound } from 'lucide-react'
import { useState } from 'react'

import type { ChatMessage } from '@/types'

function evidenceTitle(title: string, index: number) {
  const cleanTitle = title.trim()
  if (!cleanTitle || cleanTitle.toLowerCase() === 'graph') {
    return `Memory evidence ${index + 1}`
  }
  return cleanTitle
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [showReasoning, setShowReasoning] = useState(false)

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
      {message.query_type === 'temporal' ? (
        <div className="mb-3 inline-flex rounded-full border border-white/10 bg-white/[0.045] px-3 py-1 text-xs font-medium text-white/46">
          🕐 Temporal Query
        </div>
      ) : null}
      <p className="whitespace-pre-wrap break-words text-sm leading-7 text-white/82">{message.content}</p>
      {message.reasoning ? (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setShowReasoning((value) => !value)}
            className="flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-2 text-xs font-medium text-[#d7b779] transition hover:border-[#d7b779]/30"
          >
            {showReasoning ? 'Hide Reasoning' : 'Show Reasoning'}
            <ChevronDown className={`h-3.5 w-3.5 transition ${showReasoning ? 'rotate-180' : ''}`} strokeWidth={1.7} />
          </button>
          {showReasoning ? (
            <div className="mt-3 rounded-2xl border border-white/10 bg-black/24 p-4 text-sm leading-6 text-white/62">
              {message.reasoning}
            </div>
          ) : null}
        </div>
      ) : null}
      {message.sources && message.sources.length > 0 ? (
        <div className="mt-4 space-y-2">
          {message.sources.map((source, index) => (
            <button
              key={`${source.title}-${source.excerpt}`}
              type="button"
              className="block w-full rounded-2xl border border-white/10 bg-black/18 p-3 text-left text-sm transition hover:border-[#d7b779]/35"
            >
              <span className="font-semibold text-white/78">{evidenceTitle(source.title, index)}</span>
              <span className="mt-1 block break-words text-white/42">{source.excerpt}</span>
            </button>
          ))}
        </div>
      ) : null}
      {message.related_memories && message.related_memories.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.related_memories.map((memory, index) => (
            <span key={`${memory.title}-${memory.summary}-${index}`} className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-1 text-xs text-white/56">
              {evidenceTitle(memory.title, index)}
            </span>
          ))}
        </div>
      ) : null}
      {typeof message.confidence === 'number' ? (
        <p className="mt-3 text-xs text-white/38">
          Confidence: {Math.round(message.confidence * 100)}%
        </p>
      ) : null}
      </div>
    </div>
  )
}
