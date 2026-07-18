'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { BarChart3, FileText, Loader2, LogOut, MessageCircle, Mountain, UploadCloud, Wrench } from 'lucide-react'
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
        className="glass-depth-subtle fixed left-1/2 top-[calc(0.75rem+env(safe-area-inset-top))] z-50 flex w-[calc(100vw-1rem)] max-w-[calc(100vw-1rem)] items-center justify-start gap-0 overflow-x-auto rounded-full px-1 py-2 sm:top-5 sm:w-auto sm:max-w-[calc(100vw-2rem)] sm:gap-1 sm:px-2"
      >
        {items.map((item) => {
          const active = pathname === item.href
          const pending = pendingHref === item.href
          const navigating = Boolean(pendingHref)
          const Icon = item.icon
          return (
            <button
              key={item.href}
              type="button"
              aria-current={active ? 'page' : undefined}
              aria-busy={pending}
              disabled={active || (navigating && !pending)}
              onClick={() => {
                if (active || navigating) return
                setPendingHref(item.href)
                router.push(item.href)
              }}
              className={`relative flex h-12 min-w-12 shrink-0 items-center justify-center gap-2 rounded-full px-0 text-xs font-medium transition active:scale-95 sm:h-10 sm:min-w-0 sm:px-4 ${
                active || pending ? 'text-white' : 'text-white/48 hover:text-white/84'
              } ${pending ? 'bg-[#f59e0b]/12 shadow-[0_0_30px_rgba(245,158,11,0.16),inset_0_1px_0_rgba(255,255,255,0.16)]' : ''} ${
                navigating && !pending && !active ? 'pointer-events-none opacity-45' : ''
              }`}
            >
              {active ? (
                <motion.span
                  layoutId="premium-nav"
                  className="absolute inset-0 rounded-full bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.16)]"
                />
              ) : null}
              {pending ? (
                <Loader2 className="relative h-5 w-5 animate-spin text-[#f59e0b] sm:h-4 sm:w-4" strokeWidth={1.8} />
              ) : (
                <Icon className="relative h-5 w-5 sm:h-4 sm:w-4" strokeWidth={1.6} />
              )}
              <span className="relative hidden sm:inline">{pending ? 'Opening...' : item.label}</span>
            </button>
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
          className="relative grid h-12 w-12 shrink-0 place-items-center rounded-full text-white/42 transition hover:bg-white/10 hover:text-white active:scale-95 sm:h-10 sm:w-10"
          aria-label="Sign out"
        >
          <LogOut className="h-5 w-5 sm:h-4 sm:w-4" strokeWidth={1.6} />
        </button>
      </motion.nav>
    </>
  )
}
