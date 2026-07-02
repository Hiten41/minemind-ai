'use client'

import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function BackToDashboard() {
  return (
    <Link
      href="/dashboard"
      className="glass-depth-subtle fixed left-5 top-5 z-[60] flex h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-white/62 transition hover:text-white"
      aria-label="Back to dashboard"
    >
      <ArrowLeft className="h-4 w-4" strokeWidth={1.7} />
      <span>Back</span>
    </Link>
  )
}
