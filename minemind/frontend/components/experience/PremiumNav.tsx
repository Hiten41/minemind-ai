'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { BarChart3, FileText, LogOut, MessageCircle, Mountain, UploadCloud, Wrench } from 'lucide-react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'

import { clearAuthToken } from '@/lib/api'

const items = [
  { href: '/dashboard', label: 'Memory', icon: Mountain },
  { href: '/chat', label: 'Ask', icon: MessageCircle },
  { href: '/documents', label: 'Files', icon: UploadCloud },
  { href: '/analytics', label: 'Signal', icon: BarChart3 },
  { href: '/incidents', label: 'Cases', icon: FileText },
  { href: '/equipment', label: 'Equipment', icon: Wrench }
]

export default function PremiumNav() {
  const pathname = usePathname()
  const router = useRouter()
  const [pendingHref, setPendingHref] = useState<string | null>(null)

  useEffect(() => {
    setPendingHref(null)
  }, [pathname])

  useEffect(() => {
    if (!pendingHref) return
    const timer = window.setTimeout(() => setPendingHref(null), 1200)
    return () => window.clearTimeout(timer)
  }, [pendingHref])

  return (
    <>
      {pendingHref ? (
        <motion.div
          className="fixed left-0 right-0 top-0 z-[60] h-[2px] origin-left bg-white/80 shadow-[0_0_18px_rgba(255,255,255,0.42)]"
          initial={{ scaleX: 0.18, opacity: 0 }}
          animate={{ scaleX: 0.82, opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.75, ease: 'easeOut' }}
        />
      ) : null}
      <motion.nav
        initial={{ x: '-50%', y: -18, opacity: 0 }}
        animate={{ x: '-50%', y: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 90, damping: 18 }}
        className="glass-depth-subtle fixed left-1/2 top-5 z-50 flex items-center gap-1 rounded-full px-2 py-2"
      >
        {items.map((item) => {
          const active = pathname === item.href
          const pending = pendingHref === item.href
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              scroll={false}
              aria-current={active ? 'page' : undefined}
              aria-busy={pending}
              onPointerDown={() => {
                if (!active) setPendingHref(item.href)
              }}
              onClick={() => {
                if (!active) setPendingHref(item.href)
              }}
              className={`relative flex h-10 items-center gap-2 rounded-full px-4 text-xs font-medium transition active:scale-95 ${
                active || pending ? 'text-white' : 'text-white/48 hover:text-white/84'
              } ${pending ? 'bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.16)]' : ''}`}
            >
              {active ? (
                <motion.span
                  layoutId="premium-nav"
                  className="absolute inset-0 rounded-full bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.16)]"
                />
              ) : null}
              <Icon className="relative h-4 w-4" strokeWidth={1.6} />
              <span className="relative">{item.label}</span>
            </Link>
          )
        })}
        <button
          type="button"
          onPointerDown={() => setPendingHref('/login')}
          onClick={() => {
            setPendingHref('/login')
            clearAuthToken()
            router.replace('/login')
          }}
          className="relative grid h-10 w-10 place-items-center rounded-full text-white/42 transition hover:bg-white/10 hover:text-white active:scale-95"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.6} />
        </button>
      </motion.nav>
    </>
  )
}
