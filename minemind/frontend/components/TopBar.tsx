'use client'

import { usePathname } from 'next/navigation'
import { useState } from 'react'

import { improveMemory } from '@/lib/api'

function pageName(pathname: string): string {
  const raw = pathname.split('/').filter(Boolean)[0] ?? 'dashboard'
  return raw
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export default function TopBar() {
  const pathname = usePathname()
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [error, setError] = useState('')

  async function handleImprove() {
    setStatus('loading')
    setError('')
    try {
      await improveMemory()
      setStatus('done')
      setTimeout(() => setStatus('idle'), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enrich memory')
      setStatus('error')
    }
  }

  return (
    <header className="flex h-[60px] items-center justify-between border-b border-card-border bg-background px-8">
      <div>
        <h1 className="text-lg font-semibold text-white">{pageName(pathname)}</h1>
        {error ? <p className="text-xs text-danger">{error}</p> : null}
      </div>
      <button
        type="button"
        onClick={handleImprove}
        disabled={status === 'loading'}
        className="rounded-lg border border-white/15 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status === 'loading' ? 'Enriching...' : status === 'done' ? 'Done' : 'Enrich Memory'}
      </button>
    </header>
  )
}
