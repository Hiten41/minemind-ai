'use client'

import { motion } from 'framer-motion'
import { LockKeyhole, Mail, Phone, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { FormEvent, useState } from 'react'

import { loginUser, registerUser } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [mobile, setMobile] = useState('')
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'register') {
        await registerUser({ name, email, mobile, password })
      } else {
        await loginUser({ identifier, password })
      }
      router.replace('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="premium-bg noise-mask relative grid min-h-screen place-items-center overflow-hidden px-4 py-10 text-white sm:px-6 sm:py-12">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_18%,rgba(215,183,121,0.16),transparent_28%),radial-gradient(circle_at_80%_76%,rgba(96,119,139,0.18),transparent_32%)]" />
      <motion.section
        initial={{ opacity: 0, y: 18, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        className="glass-depth relative z-10 w-full max-w-[500px] rounded-[32px] p-6 sm:rounded-[36px] sm:p-7"
      >
        <img
          src="/logo.svg"
          alt="MineMind AI logo"
          className="mx-auto h-20 w-20 rounded-[24px] shadow-[0_0_60px_rgba(245,158,11,0.18)] sm:h-24 sm:w-24"
        />
        <div className="mt-6 text-center">
          <p className="tracked-label text-[10px] text-[#f59e0b]/72">The operating brain for a mine</p>
          <h1 className="mt-3 text-4xl font-bold text-white sm:text-5xl">MineMind AI</h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-white/50">
            Permanent AI memory for mining operations. Upload regulations, manuals, and incident reports &mdash; MineMind remembers everything forever and answers safety questions with evidence.
          </p>
        </div>

        <div className="mt-7 grid grid-cols-2 gap-2 rounded-full border border-white/10 bg-black/18 p-1">
          {(['login', 'register'] as const).map((item) => (
            <button
              key={item}
              type="button"
              onPointerDown={() => setMode(item)}
              onClick={() => setMode(item)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition active:scale-95 ${
                mode === item
                  ? 'bg-white text-black'
                  : 'text-white/48 hover:text-white'
              }`}
            >
              {item === 'login' ? 'Sign in' : 'Create'}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-6 space-y-3">
          {mode === 'register' ? (
            <>
              <Field icon={UserRound} placeholder="Full name" value={name} onChange={setName} />
              <Field icon={Mail} type="email" placeholder="Email address" value={email} onChange={setEmail} />
              <Field icon={Phone} placeholder="Mobile number" value={mobile} onChange={setMobile} />
            </>
          ) : (
            <Field icon={Mail} placeholder="Email or mobile number" value={identifier} onChange={setIdentifier} />
          )}
          <Field icon={LockKeyhole} type="password" placeholder="Password" value={password} onChange={setPassword} />

          {error ? (
            <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="mt-2 w-full rounded-full bg-[#f59e0b] px-5 py-4 text-sm font-semibold text-black shadow-[0_0_42px_rgba(245,158,11,0.2)] transition hover:bg-white active:scale-[0.98] disabled:cursor-wait disabled:opacity-55"
          >
            {loading ? 'Securing...' : mode === 'login' ? 'Enter MineMind' : 'Create Private Vault'}
          </button>
        </form>
      </motion.section>
    </main>
  )
}

function Field({
  icon: Icon,
  value,
  onChange,
  placeholder,
  type = 'text'
}: {
  icon: LucideIcon
  value: string
  onChange: (value: string) => void
  placeholder: string
  type?: string
}) {
  return (
    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.045] px-4 py-3 text-white/70 transition focus-within:border-[#d7b779]/40">
      <Icon className="h-4 w-4 shrink-0 text-[#d7b779]" strokeWidth={1.5} />
      <input
        required
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-white/30"
      />
    </label>
  )
}
