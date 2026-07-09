'use client'

import { motion, type Variants } from 'framer-motion'
import { Activity, AlertTriangle, BrainCircuit, Database, FileStack, Radar } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

import PremiumNav from '@/components/experience/PremiumNav'
import { getAnalytics } from '@/lib/api'
import type { AnalyticsData } from '@/types'

const pageVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.08
    }
  }
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.62, ease: [0.22, 1, 0.36, 1] as const }
  }
}

const typeColors = ['#d7b779', '#8fb8d8', '#f07167', '#7ed6a5', '#b9a7ff']

function compactNumber(value: number) {
  return new Intl.NumberFormat('en-IN', {
    notation: value >= 10000 ? 'compact' : 'standard',
    maximumFractionDigits: 1
  }).format(value)
}

function percent(value: number, total: number) {
  if (total <= 0) return 0
  return Math.round((value / total) * 100)
}

function emptyAnalytics(): AnalyticsData {
  return {
    total_documents: 0,
    total_queries: 0,
    incidents_count: 0,
    equipment_count: 0,
    memory_nodes: 0,
    recent_activity: [],
    incidents_per_month: [],
    document_types: []
  }
}

function MetricCard({
  label,
  value,
  detail,
  tone,
  icon: Icon
}: {
  label: string
  value: string
  detail: string
  tone: string
  icon: typeof Activity
}) {
  return (
    <motion.article
      variants={itemVariants}
      whileHover={{ y: -4 }}
      className="group relative overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.055] p-5 shadow-[0_24px_90px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl transition hover:border-white/20 hover:bg-white/[0.075]"
    >
      <div className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/28 to-transparent opacity-70" />
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="tracked-label text-[9px] text-white/36">{label}</p>
          <p className="mt-4 text-4xl font-semibold tracking-tight text-white">{value}</p>
        </div>
        <div
          className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-white/10 bg-black/24"
          style={{ color: tone }}
        >
          <Icon className="h-5 w-5" strokeWidth={1.55} />
        </div>
      </div>
      <p className="mt-5 text-sm leading-6 text-white/48">{detail}</p>
    </motion.article>
  )
}

function SectionShell({
  eyebrow,
  title,
  children,
  className = ''
}: {
  eyebrow: string
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-[32px] border border-white/10 bg-white/[0.045] p-5 shadow-[0_28px_110px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.09)] backdrop-blur-2xl ${className}`}
    >
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <p className="tracked-label text-[9px] text-white/32">{eyebrow}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-white/88">{title}</h2>
        </div>
      </div>
      {children}
    </section>
  )
}

function LoadingState() {
  return (
    <main className="premium-bg noise-mask relative grid min-h-screen place-items-center overflow-x-hidden px-4 text-white sm:px-6">
      <PremiumNav />
      <div className="relative z-10 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-[24px] border border-[#d7b779]/24 bg-[#d7b779]/10 text-[#d7b779]">
          <Radar className="h-7 w-7 animate-pulse" strokeWidth={1.45} />
        </div>
        <p className="tracked-label mt-6 text-[10px] text-white/38">Reading Signal</p>
        <p className="mt-3 text-lg font-medium text-white/78">Preparing analytics...</p>
      </div>
    </main>
  )
}

export default function AnalyticsPage() {
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getAnalytics()
      .then(setAnalyticsData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Analytics failed'))
      .finally(() => setLoading(false))
  }, [])

  const data = analyticsData ?? emptyAnalytics()
  const documentTypes = data.document_types
  const monthlyData = data.incidents_per_month
  const totalTypedDocs = useMemo(
    () => documentTypes.reduce((sum, item) => sum + item.value, 0),
    [documentTypes]
  )
  const topType = useMemo(
    () => [...documentTypes].sort((a, b) => b.value - a.value)[0],
    [documentTypes]
  )
  const nodesPerDoc = data.total_documents > 0
    ? Math.round(data.memory_nodes / data.total_documents)
    : 0
  const chartMonths = monthlyData.length > 0
    ? monthlyData
    : [{ month: 'No data', count: 0 }]
  const pieData = documentTypes.length > 0
    ? documentTypes
    : [{ name: 'No documents', value: 1 }]

  if (loading) return <LoadingState />

  return (
    <motion.main
      variants={pageVariants}
      initial="hidden"
      animate="show"
      className="premium-bg noise-mask relative min-h-screen overflow-x-hidden px-4 pb-10 pt-24 text-white sm:px-6 sm:pb-12 sm:pt-28"
    >
      <PremiumNav />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(180deg,rgba(255,255,255,0.025)_1px,transparent_1px)] bg-[size:96px_96px] opacity-35" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#d7b779]/30 to-transparent" />

      <div className="relative z-10 mx-auto max-w-7xl">
        <motion.header variants={itemVariants}>
          <div>
            <p className="tracked-label text-[10px] text-[#d7b779]/70">Signal Analytics</p>
            <h1 className="metal-text mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-6xl">
              Analytics
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-white/48">
              Trends and patterns across your uploaded documents and incident reports.
            </p>
          </div>
        </motion.header>

        {error ? (
          <motion.div
            variants={itemVariants}
            className="mt-6 rounded-[22px] border border-red-400/20 bg-red-500/10 px-5 py-4 text-sm text-red-100"
          >
            {error}
          </motion.div>
        ) : null}

        <section className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Documents"
            value={compactNumber(data.total_documents)}
            detail={`Top Source Type: ${topType?.name ? topType.name.charAt(0).toUpperCase() + topType.name.slice(1) : 'None'}`}
            tone="#8fb8d8"
            icon={FileStack}
          />
          <MetricCard
            label="Memory Nodes"
            value={compactNumber(data.memory_nodes)}
            detail={`Average Density: ${compactNumber(nodesPerDoc)} nodes/doc`}
            tone="#d7b779"
            icon={BrainCircuit}
          />
          <MetricCard
            label="Incidents"
            value={compactNumber(data.incidents_count)}
            detail={`${percent(data.incidents_count, data.total_documents)}% of documents are incident records`}
            tone="#f07167"
            icon={AlertTriangle}
          />
          <MetricCard
            label="Equipment"
            value={compactNumber(data.equipment_count)}
            detail={`Equipment Linked: ${percent(data.equipment_count, data.total_documents)}% of documents`}
            tone="#7ed6a5"
            icon={Database}
          />
        </section>

        <div className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.85fr)]">
          <SectionShell eyebrow="Monthly Trend" title="Incident capture over time" className="min-h-[430px]">
            <div className="h-[340px] min-w-0 overflow-x-auto">
              <div className="h-full min-w-[260px] sm:min-w-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartMonths} margin={{ top: 12, right: 8, left: -18, bottom: 8 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="month" stroke="rgba(255,255,255,0.38)" tickLine={false} axisLine={false} />
                  <YAxis stroke="rgba(255,255,255,0.34)" tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: 'rgba(215,183,121,0.08)' }}
                    contentStyle={{
                      background: 'rgba(8,8,8,0.92)',
                      border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: 18,
                      color: '#ffffff',
                      boxShadow: '0 20px 80px rgba(0,0,0,0.48)'
                    }}
                  />
                  <Bar dataKey="count" fill="#d7b779" radius={[12, 12, 4, 4]} maxBarSize={74} />
                </BarChart>
              </ResponsiveContainer>
              </div>
            </div>
          </SectionShell>

          <SectionShell eyebrow="Source Mix" title="Document distribution" className="min-h-[430px]">
            <div className="h-[238px] min-w-0 overflow-hidden">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={70}
                    outerRadius={102}
                    paddingAngle={4}
                  >
                    {pieData.map((entry, index) => (
                      <Cell
                        key={entry.name}
                        fill={documentTypes.length > 0 ? typeColors[index % typeColors.length] : 'rgba(255,255,255,0.16)'}
                        stroke="rgba(0,0,0,0.35)"
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(8,8,8,0.92)',
                      border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: 18,
                      color: '#ffffff'
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-5 space-y-3">
              {documentTypes.length > 0 ? documentTypes.map((item, index) => (
                <div key={item.name} className="flex items-center gap-3">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: typeColors[index % typeColors.length] }}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm capitalize text-white/62">{item.name}</span>
                  <span className="text-sm font-medium text-white/84">{item.value}</span>
                </div>
              )) : (
                <p className="rounded-2xl border border-white/10 bg-black/18 px-4 py-3 text-sm text-white/46">
                  Upload files to build a source mix.
                </p>
              )}
            </div>
          </SectionShell>
        </div>
      </div>
    </motion.main>
  )
}
