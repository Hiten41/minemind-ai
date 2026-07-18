'use client'

import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function BackToDashboard() {
  return (
    <Link
      href="/dashboard"
      className="glass-depth-subtle fixed left-5 top-5 z-[60] hidden h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-white/62 transition hover:text-white sm:flex"
      aria-label="Back to dashboard"
    >
      <ArrowLeft className="h-4 w-4" strokeWidth={1.7} />
      <span className="hidden sm:inline">Back</span>
    </Link>
  )
}
