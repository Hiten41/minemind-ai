'use client'

import { motion } from 'framer-motion'
import { AlertTriangle, ArrowUpRight, Check, Loader2, Search, Send, UploadCloud, Wand2 } from 'lucide-react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import MemoryUploadRail from '@/components/experience/MemoryUploadRail'
import PremiumNav from '@/components/experience/PremiumNav'
import { getAlerts, getAnalytics } from '@/lib/api'
import type { AnalyticsData, RiskAlert, RiskLevel } from '@/types'

const KnowledgeCrystal = dynamic(() => import('@/components/experience/KnowledgeCrystal'), {
  ssr: false,
  loading: () => null
})

const instantGlobeNodes: Array<[number, number, number, string]> = [
  [124, 208, 5, '#f1d18d'],
  [212, 124, 4, '#a7adb2'],
  [306, 196, 6, '#f1d18d'],
  [256, 302, 5, '#a7adb2'],
  [132, 282, 4, '#f1d18d'],
  [230, 216, 3, '#ffffff']
]

function InstantKnowledgeGlobe() {
  return (
    <div className="pointer-events-none absolute inset-0 grid place-items-center">
      <div className="relative h-[min(420px,48vh)] w-[min(420px,48vh)] rounded-full">
        <div className="absolute inset-0 rounded-full bg-[#d7b779]/10 blur-3xl" />
        <div className="absolute inset-[12%] rounded-full border border-[#d7b779]/10 bg-[radial-gradient(circle_at_45%_38%,rgba(215,183,121,0.2),rgba(255,255,255,0.025)_42%,transparent_72%)] shadow-[inset_0_0_90px_rgba(215,183,121,0.1),0_0_80px_rgba(215,183,121,0.08)]" />
        <div className="absolute inset-[16%] animate-[spin_18s_linear_infinite] rounded-full border border-white/[0.08]" />
        <div className="absolute inset-[24%] animate-[spin_14s_linear_infinite_reverse] rounded-full border border-[#d7b779]/[0.12]" />
        <svg viewBox="0 0 420 420" className="absolute inset-0 h-full w-full animate-[spin_28s_linear_infinite] opacity-70">
          <line x1="124" y1="208" x2="212" y2="124" stroke="#d7b779" strokeOpacity="0.2" strokeWidth="1" />
          <line x1="212" y1="124" x2="306" y2="196" stroke="#d7b779" strokeOpacity="0.16" strokeWidth="1" />
          <line x1="306" y1="196" x2="256" y2="302" stroke="#d7b779" strokeOpacity="0.16" strokeWidth="1" />
          <line x1="256" y1="302" x2="132" y2="282" stroke="#d7b779" strokeOpacity="0.2" strokeWidth="1" />
          <line x1="132" y1="282" x2="124" y2="208" stroke="#d7b779" strokeOpacity="0.16" strokeWidth="1" />
          <line x1="124" y1="208" x2="256" y2="302" stroke="#ffffff" strokeOpacity="0.09" strokeWidth="1" />
          <line x1="212" y1="124" x2="256" y2="302" stroke="#ffffff" strokeOpacity="0.08" strokeWidth="1" />
          {instantGlobeNodes.map(([cx, cy, r, fill]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} fill={fill} opacity="0.82" />
          ))}
        </svg>
      </div>
    </div>
  )
}

function FloatingMetric({
  label,
  value,
  className
}: {
  label: string
  value: string
  className: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className={`fixed z-30 hidden md:block ${className}`}
    >
      <p className="tracked-label text-[10px] text-white/38">{label}</p>
      <p className="mt-2 text-sm font-medium text-white/70">{value}</p>
    </motion.div>
  )
}

const riskStyles: Record<Exclude<RiskLevel, 'none'>, string> = {
  high: 'border-red-400/55 bg-red-500/[0.09] text-red-100',
  medium: 'border-yellow-300/55 bg-yellow-400/[0.09] text-yellow-100',
  low: 'border-orange-300/55 bg-orange-400/[0.09] text-orange-100'
}

function riskRank(level: RiskLevel): number {
  return level === 'high' ? 3 : level === 'medium' ? 2 : level === 'low' ? 1 : 0
}

export default function DashboardPage() {
  const router = useRouter()
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [alerts, setAlerts] = useState<RiskAlert[]>([])
  const [analyticsState, setAnalyticsState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [alertsState, setAlertsState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [question, setQuestion] = useState('')
  const [queryPulse, setQueryPulse] = useState(0)
  const [optimizePulse, setOptimizePulse] = useState(0)
  const [isDraggingFile, setIsDraggingFile] = useState(false)
  const [crystalReady, setCrystalReady] = useState(false)
  const [pendingRoute, setPendingRoute] = useState<string | null>(null)

  const refreshDashboardData = useCallback(() => {
    setAnalyticsState('loading')
    setAlertsState('loading')

    getAnalytics()
      .then((data) => {
        setAnalytics(data)
        setAnalyticsState('ready')
      })
      .catch(() => {
        setAnalytics(null)
        setAnalyticsState('error')
      })
    getAlerts()
      .then((items) => {
        setAlerts(
          [...items].sort((left, right) => riskRank(right.risk_level) - riskRank(left.risk_level))
        )
        setAlertsState('ready')
      })
      .catch(() => {
        setAlerts([])
        setAlertsState('error')
      })
  }, [])

  useEffect(() => {
    refreshDashboardData()
  }, [refreshDashboardData])

  useEffect(() => {
    function handleFocus() {
      refreshDashboardData()
    }

    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [refreshDashboardData])

  useEffect(() => {
    let dragDepth = 0

    function hasFiles(event: DragEvent) {
      return Array.from(event.dataTransfer?.types ?? []).includes('Files')
    }

    function handleDragEnter(event: DragEvent) {
      if (!hasFiles(event)) return
      event.preventDefault()
      dragDepth += 1
      setIsDraggingFile(true)
    }

    function handleDragOver(event: DragEvent) {
      if (!hasFiles(event)) return
      event.preventDefault()
      setIsDraggingFile(true)
    }

    function handleDragLeave(event: DragEvent) {
      if (!hasFiles(event)) return
      event.preventDefault()
      dragDepth = Math.max(0, dragDepth - 1)
      if (dragDepth === 0) setIsDraggingFile(false)
    }

    function handleDrop(event: DragEvent) {
      if (!hasFiles(event)) return
      event.preventDefault()
      dragDepth = 0
      setIsDraggingFile(false)
    }

    window.addEventListener('dragenter', handleDragEnter)
    window.addEventListener('dragover', handleDragOver)
    window.addEventListener('dragleave', handleDragLeave)
    window.addEventListener('drop', handleDrop)

    return () => {
      window.removeEventListener('dragenter', handleDragEnter)
      window.removeEventListener('dragover', handleDragOver)
      window.removeEventListener('dragleave', handleDragLeave)
      window.removeEventListener('drop', handleDrop)
    }
  }, [])

  function ask() {
    const trimmed = question.trim()
    if (!trimmed) return
    setQueryPulse((current) => current + 1)
    const href = `/chat?q=${encodeURIComponent(trimmed)}`
    setPendingRoute(href)
    router.push(href)
  }

  const documents = analytics?.total_documents ?? 0
  const incidentReports = analytics?.incidents_count ?? 0
  const documentsLabel = (() => {
    if (analyticsState === 'loading') return 'Loading...'
    if (analyticsState === 'error') return 'Unavailable'
    return `${documents.toLocaleString()} sources`
  })()
  const incidentsLabel = (() => {
    if (analyticsState === 'loading') return 'Loading...'
    if (analyticsState === 'error') return 'Unavailable'
    return `${incidentReports.toLocaleString()} uploaded cases`
  })()

  return (
    <main className="premium-bg noise-mask relative min-h-screen overflow-x-hidden text-white md:h-screen md:min-h-[760px] md:overflow-hidden">
      <PremiumNav />
      <MemoryUploadRail onUploadComplete={refreshDashboardData} />

      <motion.div
        animate={{
          filter: isDraggingFile ? 'blur(18px)' : 'blur(0px)',
          opacity: isDraggingFile ? 0.68 : 1
        }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.18)_42%,rgba(0,0,0,0.84)_100%)]"
      />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[760px] w-[760px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#d7b779]/[0.055] blur-3xl" />

      <FloatingMetric
        label="Documents Indexed"
        value={documentsLabel}
        className="left-10 top-28"
      />
      <FloatingMetric
        label="Incident Reports"
        value={incidentsLabel}
        className="right-10 top-28 text-right"
      />
      <FloatingMetric
        label="Model Context"
        value="Cognee memory graph"
        className="bottom-10 left-10"
      />
      <FloatingMetric
        label="Interface"
        value="Spatial query mode"
        className="bottom-10 right-10 text-right"
      />

      <section className="relative z-30 mx-auto w-[calc(100vw-1.5rem)] pt-[520px] md:fixed md:left-10 md:top-44 md:w-[min(360px,calc(100vw-40px))] md:pt-0">
        <div className="glass-depth-subtle rounded-[26px] border border-white/10 bg-black/18 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="tracked-label text-[10px] text-white/38">Real-Time Alerts</p>
              <h2 className="mt-2 text-sm font-semibold text-white/82">Risk signals</h2>
            </div>
            <AlertTriangle className="h-5 w-5 text-[#d7b779]" strokeWidth={1.55} />
          </div>

          <div className="mt-4 space-y-3">
            {alertsState === 'loading' ? (
              <div className="rounded-[20px] border border-white/10 bg-white/[0.04] px-3 py-4 text-sm text-white/52">
                Loading risk signals...
              </div>
            ) : alertsState === 'error' ? (
              <div className="rounded-[20px] border border-amber-300/30 bg-amber-400/[0.08] px-3 py-4 text-sm text-amber-100">
                Risk signals could not be loaded right now.
              </div>
            ) : alerts.length > 0 ? alerts.slice(0, 3).map((alert) => (
              <article
                key={alert.id}
                className={`rounded-[20px] border p-3 ${riskStyles[alert.risk_level]}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold text-white/86">{alert.name}</h3>
                    <p className="mt-2 text-xs leading-5 text-white/54">
                      {alert.risk_signals.violations} safety violations, {alert.risk_signals.equipment} equipment issues, {alert.risk_signals.hazards} hazards found
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full border border-current/30 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]">
                    {alert.risk_level}
                  </span>
                </div>
                <button
                  type="button"
                  onPointerDown={() => router.push(`/chat?q=${encodeURIComponent(`Analyze the risks in ${alert.name}`)}`)}
                  onClick={() => router.push(`/chat?q=${encodeURIComponent(`Analyze the risks in ${alert.name}`)}`)}
                  className="mt-3 flex items-center gap-1 text-xs font-medium text-white/72 transition hover:text-white"
                >
                  Ask MineMind about this
                  <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.7} />
                </button>
              </article>
            )) : (
              <div className="rounded-[20px] border border-emerald-300/30 bg-emerald-400/[0.08] px-3 py-4 text-sm text-emerald-100">
                <div className="flex items-center gap-2">
                  <Check className="h-4 w-4" strokeWidth={1.8} />
                  <span>No risk signals detected in current documents</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="absolute inset-x-0 top-0 z-10 flex min-h-[520px] flex-col items-center px-4 pb-24 pt-24 md:relative md:h-full md:min-h-0 md:justify-center md:px-8 md:pb-28">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-none absolute top-24 max-w-[calc(100vw-2rem)] text-center md:top-[13vh] md:max-w-3xl"
        >
          <div className="mx-auto flex w-fit items-center gap-3 rounded-full border border-[#f59e0b]/20 bg-black/24 px-4 py-2 shadow-[0_0_44px_rgba(245,158,11,0.12)] backdrop-blur-xl">
            <img src="/logo.svg" alt="MineMind AI logo" className="h-8 w-8 rounded-xl" />
            <span className="tracked-label text-[11px] text-[#f59e0b]/78">MineMind AI</span>
          </div>
          <h1 className="metal-text mt-4 text-4xl font-bold leading-[1.02] tracking-tight sm:text-5xl md:text-6xl">
            The operating brain for a mine
          </h1>
          <p className="mx-auto mt-5 max-w-md text-sm leading-6 text-white/48 sm:text-base sm:leading-7">
            Permanent AI memory for mining operations. Upload regulations, manuals, and incident reports &mdash; MineMind remembers everything forever and answers safety questions with evidence.
          </p>
        </motion.div>

        <motion.div
          initial={{ x: '-50%', y: '-50%', opacity: 0, scale: 0.94 }}
          animate={{
            x: '-50%',
            y: '-50%',
            opacity: isDraggingFile ? 0.3 : 1,
            scale: isDraggingFile ? 0.96 : 1
          }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
          className="absolute left-1/2 top-[60%] h-[260px] w-[min(92vw,560px)] sm:h-[340px] md:top-[54%] md:h-[58vh] md:max-h-[590px] md:min-h-[420px] md:w-[min(78vw,880px)]"
        >
          <motion.div
            initial={false}
            animate={{ opacity: crystalReady ? 0 : 1, scale: crystalReady ? 0.98 : 1 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0"
          >
            <InstantKnowledgeGlobe />
          </motion.div>
          <motion.div
            initial={false}
            animate={{ opacity: crystalReady ? 1 : 0 }}
            transition={{ duration: 0.75, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0"
          >
            <KnowledgeCrystal
              queryPulse={queryPulse}
              optimizePulse={optimizePulse}
              onReady={() => setCrystalReady(true)}
            />
          </motion.div>
        </motion.div>

        <motion.button
          type="button"
          onClick={() => setOptimizePulse((current) => current + 1)}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: isDraggingFile ? 0 : 1, y: 0 }}
          transition={{ delay: 0.65 }}
          className="glass-depth-subtle fixed right-4 top-[430px] z-30 hidden items-center gap-2 rounded-full px-4 py-3 text-xs font-medium text-white/58 transition hover:text-white/86 sm:flex md:right-[13vw] md:top-[34vh]"
        >
          <Wand2 className="h-4 w-4 text-[#d7b779]" strokeWidth={1.5} />
          Optimize Memory
        </motion.button>

        <motion.div
          initial={{ x: '-50%', opacity: 0, y: 28, scale: 0.98 }}
          animate={{ x: '-50%', opacity: 1, y: 0, scale: 1 }}
          transition={{ type: 'spring', stiffness: 88, damping: 20, delay: 0.28 }}
          className="glass-depth amber-aura fixed bottom-5 left-1/2 z-40 w-[min(760px,calc(100vw-1.5rem))] rounded-[24px] p-2 md:bottom-[8vh] md:rounded-[28px]"
        >
          <form
            className="flex items-center gap-2 sm:gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              ask()
            }}
          >
            <div className="hidden h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/[0.07] text-white/58 sm:grid">
              <Search className="h-5 w-5" strokeWidth={1.55} />
            </div>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask MineMind about incidents, regulations, or equipment history"
              className="soft-focus-ring h-12 min-w-0 flex-1 bg-transparent px-2 text-sm text-white placeholder:text-white/34 sm:h-14 sm:px-0 sm:text-[15px]"
            />
            <button
              type="submit"
              disabled={Boolean(pendingRoute)}
              className="group grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[#d7b779] text-black shadow-[0_0_38px_rgba(215,183,121,0.28)] transition hover:scale-[1.03] active:scale-95 disabled:cursor-wait disabled:opacity-70"
              aria-label="Submit query"
            >
              {pendingRoute ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
              ) : (
                <Send className="h-4 w-4 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" strokeWidth={1.8} />
              )}
            </button>
          </form>
        </motion.div>

        <motion.button
          type="button"
          onPointerDown={() => setPendingRoute('/documents')}
          onClick={() => router.push('/documents')}
          initial={{ x: '-50%', opacity: 0 }}
          animate={{ x: '-50%', opacity: 1 }}
          transition={{ delay: 0.9 }}
          className="fixed bottom-1 left-1/2 z-30 hidden items-center gap-2 text-sm text-white/42 transition hover:text-white/80 active:scale-95 md:flex md:bottom-[2.8vh]"
        >
          Manage uploaded files
          <UploadCloud className="h-4 w-4" strokeWidth={1.6} />
          <ArrowUpRight className="h-4 w-4" strokeWidth={1.6} />
        </motion.button>
      </section>

      <motion.div
        initial={false}
        animate={{
          opacity: isDraggingFile ? 1 : 0,
          backdropFilter: isDraggingFile ? 'blur(40px)' : 'blur(0px)'
        }}
        style={{ pointerEvents: isDraggingFile ? 'auto' : 'none' }}
        transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
        className="fixed inset-0 z-[80] grid place-items-center bg-black/42"
      >
        <motion.div
          initial={false}
          animate={{
            scale: isDraggingFile ? 1 : 0.96,
            y: isDraggingFile ? 0 : 18
          }}
          transition={{ type: 'spring', stiffness: 96, damping: 18 }}
          className="glass-depth amber-aura grid h-[min(540px,70vh)] w-[min(920px,82vw)] place-items-center rounded-[42px] border border-[#d7b779]/35"
        >
          <p className="tracked-label max-w-2xl text-center text-2xl font-bold leading-[1.55] text-white/82 md:text-3xl">
            Drop incident reports to expand MineMind Memory
          </p>
        </motion.div>
      </motion.div>
    </main>
  )
}
