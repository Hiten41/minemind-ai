'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { clearAuthToken, getAuthToken, getCurrentUser } from '@/lib/api'

const publicPaths = new Set(['/login'])

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [ready, setReady] = useState(() => publicPaths.has(pathname))

  useEffect(() => {
    let cancelled = false
    const timeout = window.setTimeout(() => {
      if (!cancelled) setReady(true)
    }, 2500)

    async function checkSession() {
      if (publicPaths.has(pathname)) {
        window.clearTimeout(timeout)
        setReady(true)
        return
      }

      if (!getAuthToken()) {
        window.clearTimeout(timeout)
        setReady(false)
        router.replace('/login')
        return
      }

      try {
        await getCurrentUser()
        if (!cancelled) {
          window.clearTimeout(timeout)
          setReady(true)
        }
      } catch {
        if (cancelled) return
        window.clearTimeout(timeout)
        setReady(false)
        clearAuthToken()
        router.replace('/login')
      }
    }

    setReady(publicPaths.has(pathname))
    void checkSession()

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [pathname, router])

  if (!ready && !publicPaths.has(pathname)) {
    return (
      <div className="premium-bg grid min-h-screen place-items-center text-white/48">
        Securing MineMind...
      </div>
    )
  }

  return children
}
