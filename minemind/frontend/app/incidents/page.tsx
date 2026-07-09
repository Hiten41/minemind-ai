'use client'

import { motion, type Variants } from 'framer-motion'
import { AlertTriangle, ArrowRight, FileText, Layers3, ShieldCheck, UploadCloud, X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import PremiumNav from '@/components/experience/PremiumNav'
import { getDocumentsPage } from '@/lib/api'
import type { Document } from '@/types'

type IncidentCase = {
  id: string
  title: string
  date: string
  status: string
  nodes: number
  datasetName: string
}

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

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  })
}

function toIncidentCase(doc: Document, index: number): IncidentCase {
  return {
    id: `CASE-${String(index + 1).padStart(3, '0')}`,
    title: doc.name,
    date: formatDate(doc.uploaded_at),
    status: doc.status,
    nodes: doc.node_count,
    datasetName: doc.dataset_name
  }
}

function LoadingBlock() {
  return (
    <div className="rounded-[28px] border border-white/10 bg-white/[0.045] p-6 text-center shadow-[0_28px_110px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.09)] backdrop-blur-2xl sm:rounded-[32px] sm:p-8">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-white/10 bg-white/[0.06] text-white/62">
        <AlertTriangle className="h-6 w-6 animate-pulse" strokeWidth={1.45} />
      </div>
      <p className="tracked-label mt-5 text-[10px] text-white/34">Reading Cases</p>
      <p className="mt-3 text-sm text-white/54">Loading uploaded incident reports...</p>
    </div>
  )
}

export default function IncidentsPage() {
  const router = useRouter()
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedCase, setSelectedCase] = useState<IncidentCase | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [totalCases, setTotalCases] = useState(0)
  const [hasMoreCases, setHasMoreCases] = useState(false)

  useEffect(() => {
    let cancelled = false
    const timeout = window.setTimeout(() => {
      if (!cancelled) {
        setError('Incident reports are taking too long to load. Refresh or sign in again.')
        setLoading(false)
      }
    }, 8000)

    getDocumentsPage({ limit: 50, type: 'incident' })
      .then((page) => {
        if (!cancelled) {
          setDocuments(page.items)
          setTotalCases(page.total)
          setHasMoreCases(page.has_more)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load incident reports')
        }
      })
      .finally(() => {
        if (!cancelled) {
          window.clearTimeout(timeout)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [])

  async function loadMoreCases() {
    setLoadingMore(true)
    setError('')
    try {
      const page = await getDocumentsPage({ limit: 50, offset: documents.length, type: 'incident' })
      setDocuments((current) => [...current, ...page.items])
      setTotalCases(page.total)
      setHasMoreCases(page.has_more)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more incident reports')
    } finally {
      setLoadingMore(false)
    }
  }

  const cases = useMemo(
    () => documents
      .filter((doc) => doc.type === 'incident')
      .map(toIncidentCase),
    [documents]
  )
  const totalNodes = useMemo(
    () => cases.reduce((sum, item) => sum + item.nodes, 0),
    [cases]
  )

  useEffect(() => {
    if (!loading && cases.length === 1) {
      setSelectedCase((current) => current ?? cases[0])
    }
  }, [cases, loading])

  return (
    <motion.main
      variants={pageVariants}
      initial="hidden"
      animate="show"
      className="premium-bg noise-mask relative min-h-screen overflow-x-hidden px-4 pb-10 pt-24 text-white sm:px-6 sm:pb-12 sm:pt-28"
    >
      <PremiumNav />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(180deg,rgba(255,255,255,0.025)_1px,transparent_1px)] bg-[size:112px_112px] opacity-30" />
      <div className="pointer-events-none absolute right-[8%] top-[18%] h-[min(420px,82vw)] w-[min(420px,82vw)] rounded-full bg-[#8fb8d8]/[0.07] blur-3xl" />
      <div className="pointer-events-none absolute left-[8%] bottom-[8%] h-[min(360px,78vw)] w-[min(360px,78vw)] rounded-full bg-white/[0.04] blur-3xl" />

      <div className="relative z-10 mx-auto max-w-7xl">
        <motion.header variants={itemVariants} className="flex flex-col justify-between gap-7 lg:flex-row lg:items-end">
          <div>
            <p className="tracked-label text-[10px] text-white/40">Cases</p>
            <h1 className="metal-text mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-6xl">
              Incidents
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-white/48">
              Real incident reports from your uploaded documents, ready for recall, regulation matching, and follow-up analysis.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-right">
            <div className="rounded-3xl border border-white/10 bg-white/[0.045] px-5 py-4 backdrop-blur-2xl">
              <p className="tracked-label text-[9px] text-white/32">Reports</p>
              <p className="mt-2 text-2xl font-semibold text-white/86">{totalCases || cases.length}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.045] px-5 py-4 backdrop-blur-2xl">
              <p className="tracked-label text-[9px] text-white/32">Nodes</p>
              <p className="mt-2 text-2xl font-semibold text-white/86">{totalNodes.toLocaleString()}</p>
            </div>
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

        <div className="mt-8 grid gap-4 sm:mt-10 lg:grid-cols-[minmax(0,1fr)_390px] lg:gap-6">
          <motion.section variants={itemVariants} className="lg:min-h-[520px]">
            {loading ? (
              <LoadingBlock />
            ) : cases.length > 0 ? (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  {cases.map((item, index) => (
                    <motion.button
                      key={item.datasetName}
                      type="button"
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.45, delay: index * 0.035 }}
                      whileHover={{ y: -5 }}
                      whileTap={{ scale: 0.985 }}
                      onClick={() => setSelectedCase(item)}
                      className={`group relative overflow-hidden rounded-[30px] border p-5 text-left shadow-[0_24px_90px_rgba(0,0,0,0.38),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl transition duration-300 ${
                        selectedCase?.datasetName === item.datasetName
                          ? 'border-white/32 bg-white/[0.09]'
                          : 'border-white/10 bg-white/[0.045] hover:border-white/22 hover:bg-white/[0.07]'
                      }`}
                    >
                      <div className="pointer-events-none absolute inset-x-7 top-0 h-px bg-gradient-to-r from-transparent via-white/24 to-transparent" />
                      <div className="flex items-start justify-between gap-4">
                        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-white/10 bg-white/[0.06] text-white/68">
                          <FileText className="h-5 w-5" strokeWidth={1.45} />
                        </div>
                        <span className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs capitalize text-white/48">
                          {item.status}
                        </span>
                      </div>
                      <p className="tracked-label mt-6 text-[9px] text-white/32">{item.id} - {item.date}</p>
                      <h2 className="mt-3 line-clamp-2 min-h-[3.25rem] text-xl font-semibold leading-7 tracking-tight text-white/88">
                        {item.title}
                      </h2>
                      <div className="mt-6 flex items-center justify-between gap-3 text-sm">
                        <span className="text-white/34">Memory nodes</span>
                        <span className="font-medium text-white/72">{item.nodes.toLocaleString()}</span>
                      </div>
                    </motion.button>
                  ))}
                </div>
                {hasMoreCases ? (
                  <button
                    type="button"
                    onClick={loadMoreCases}
                    disabled={loadingMore}
                    className="mt-6 w-full rounded-full border border-white/10 bg-white/[0.055] px-5 py-3 text-sm font-medium text-white/68 transition hover:border-white/22 hover:bg-white/[0.08] disabled:cursor-wait disabled:opacity-50"
                  >
                    {loadingMore ? 'Loading more...' : 'Load more cases'}
                  </button>
                ) : null}
              </>
            ) : (
              <motion.div
                variants={itemVariants}
                className="grid min-h-[340px] place-items-center rounded-[30px] border border-white/10 bg-white/[0.045] p-6 text-center shadow-[0_28px_110px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.09)] backdrop-blur-2xl sm:min-h-[480px] sm:rounded-[36px] sm:p-10"
              >
                <div>
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl border border-white/10 bg-white/[0.06] text-white/62">
                    <UploadCloud className="h-7 w-7" strokeWidth={1.35} />
                  </div>
                  <h2 className="mt-6 text-2xl font-semibold tracking-tight text-white/86">
                    No incident reports uploaded yet
                  </h2>
                  <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-white/44">
                    Upload a document with type Incident from the Files page, and it will appear here as a real case.
                  </p>
                  <button
                    type="button"
                    onClick={() => router.push('/documents')}
                    className="mt-7 inline-flex items-center gap-2 rounded-full border border-white/14 bg-white/[0.08] px-5 py-3 text-sm font-medium text-white transition hover:border-white/26 hover:bg-white/[0.12] active:scale-95"
                  >
                    Upload Incident Report
                    <ArrowRight className="h-4 w-4" strokeWidth={1.6} />
                  </button>
                </div>
              </motion.div>
            )}
          </motion.section>

          <motion.aside
            variants={itemVariants}
            className="h-fit rounded-[32px] border border-white/10 bg-white/[0.045] p-5 shadow-[0_28px_110px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.09)] backdrop-blur-2xl"
          >
            {selectedCase ? (
              <div>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="tracked-label text-[9px] text-white/32">{selectedCase.id}</p>
                    <h2 className="mt-3 break-words text-2xl font-semibold leading-tight tracking-tight text-white">
                      {selectedCase.title}
                    </h2>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedCase(null)}
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-white/58 transition hover:bg-white/10 hover:text-white"
                    aria-label="Close selected case"
                  >
                    <X className="h-4 w-4" strokeWidth={1.5} />
                  </button>
                </div>

                <dl className="mt-7 divide-y divide-white/10 rounded-2xl border border-white/10 bg-black/18">
                  {[
                    ['Status', selectedCase.status],
                    ['Uploaded', selectedCase.date],
                    ['Memory nodes', selectedCase.nodes.toLocaleString()],
                    ['Dataset', selectedCase.datasetName]
                  ].map(([label, value]) => (
                    <div key={label} className="grid gap-2 px-4 py-3 sm:grid-cols-[120px_minmax(0,1fr)]">
                      <dt className="text-xs text-white/34">{label}</dt>
                      <dd className="break-all text-sm font-medium text-white/76">{value}</dd>
                    </div>
                  ))}
                </dl>

                <div className="mt-6 space-y-3">
                  <button
                    type="button"
                    onClick={() => router.push(`/chat?q=${encodeURIComponent(`Summarize this uploaded incident report and identify similar memories: ${selectedCase.title}`)}`)}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/14 bg-white/[0.08] px-4 py-3 text-sm font-medium text-white transition hover:border-white/26 hover:bg-white/[0.12] active:scale-[0.98]"
                  >
                    <Layers3 className="h-4 w-4" strokeWidth={1.55} />
                    Ask About This Report
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push(`/chat?q=${encodeURIComponent(`Which DGMS regulations apply to this uploaded incident report: ${selectedCase.title}`)}`)}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm font-medium text-white/74 transition hover:border-white/24 hover:text-white active:scale-[0.98]"
                  >
                    <ShieldCheck className="h-4 w-4" strokeWidth={1.55} />
                    Check DGMS Regulations
                  </button>
                  <button
                    type="button"
                    onPointerDown={() => router.push(`/chat?q=${encodeURIComponent(`Find similar incidents to ${selectedCase.title} and compare hazards, causes, and corrective actions`)}`)}
                    onClick={() => router.push(`/chat?q=${encodeURIComponent(`Find similar incidents to ${selectedCase.title} and compare hazards, causes, and corrective actions`)}`)}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm font-medium text-white/74 transition hover:border-white/24 hover:text-white active:scale-[0.98]"
                  >
                    <ArrowRight className="h-4 w-4" strokeWidth={1.55} />
                    Find Similar Incidents
                  </button>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center">
                <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-white/10 bg-white/[0.055] text-white/58">
                  <AlertTriangle className="h-6 w-6" strokeWidth={1.35} />
                </div>
                <p className="mt-5 text-lg font-semibold text-white/82">Select a case</p>
                <p className="mx-auto mt-2 max-w-xs text-sm leading-6 text-white/42">
                  Choose an uploaded incident report to inspect its memory details or ask MineMind about applicable regulations.
                </p>
              </div>
            )}
          </motion.aside>
        </div>
      </div>
    </motion.main>
  )
}
