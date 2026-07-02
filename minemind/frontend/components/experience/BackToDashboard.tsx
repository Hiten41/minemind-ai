'use client'

import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function BackToDashboard() {
  return (
    <Link
      href="/dashboard"
      className="glass-depth-subtle fixed left-3 top-16 z-[60] flex h-10 items-center gap-2 rounded-full px-3 text-sm font-medium text-white/62 transition hover:text-white sm:left-5 sm:top-5 sm:h-11 sm:px-4"
      aria-label="Back to dashboard"
    >
      <ArrowLeft className="h-4 w-4" strokeWidth={1.7} />
      <span className="hidden sm:inline">Back</span>
    </Link>
  )
}
