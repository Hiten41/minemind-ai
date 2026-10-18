'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { ApiError, clearAuthToken, getAuthToken, getCurrentUser } from '@/lib/api'

const publicPaths = new Set(['/login'])

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [ready, setReady] = useState(() => publicPaths.has(pathname))

  useEffect(() => {
    let cancelled = false

    async function checkSession() {
      if (publicPaths.has(pathname)) {
        setReady(true)
        return
      }

      if (!getAuthToken()) {
        setReady(false)
        router.replace('/login')
        return
      }

      try {
        await getCurrentUser()
        if (!cancelled) {
          setReady(true)
        }
      } catch (error) {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) {
          setReady(false)
          clearAuthToken()
          router.replace('/login')
          return
        }
        // A temporary network failure must not silently sign a user out.
        setReady(true)
      }
    }

    setReady(publicPaths.has(pathname))
    void checkSession()

    return () => {
      cancelled = true
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
