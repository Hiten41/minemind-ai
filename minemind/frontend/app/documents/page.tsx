'use client'

import { AnimatePresence, motion, useMotionValue, useSpring, useTransform, type Variants } from 'framer-motion'
import { Eye, FileText, Layers3, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import PremiumNav from '@/components/experience/PremiumNav'
import UploadZone from '@/components/upload/UploadZone'
import { forgetDataset, getDocumentsPage, uploadDocument } from '@/lib/api'
import type { Document } from '@/types'

const typeLabels = [
  { value: 'regulation', label: 'Regulation' },
  { value: 'manual', label: 'Manual' },
  { value: 'incident', label: 'Incident' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'shift', label: 'Shift' }
]

const containerVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.1
    }
  }
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 15 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.8,
      ease: [0.23, 1, 0.32, 1] as const
    }
  }
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  })
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [totalDocuments, setTotalDocuments] = useState(0)
  const [hasMoreDocuments, setHasMoreDocuments] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [selectedType, setSelectedType] = useState('regulation')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')
  const pointerX = useMotionValue(0)
  const pointerY = useMotionValue(0)
  const smoothX = useSpring(pointerX, { stiffness: 60, damping: 22 })
  const smoothY = useSpring(pointerY, { stiffness: 60, damping: 22 })
  const orbX = useTransform(smoothX, (value) => value * 24)
  const orbY = useTransform(smoothY, (value) => value * 18)
  const sheenX = useTransform(smoothX, (value) => value * -14)
  const sheenY = useTransform(smoothY, (value) => value * -10)

  useEffect(() => {
    getDocumentsPage({ limit: 50 })
      .then((page) => {
        setDocuments(page.items)
        setTotalDocuments(page.total)
        setHasMoreDocuments(page.has_more)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to fetch documents'))
  }, [])

  async function loadMoreDocuments() {
    setLoadingMore(true)
    setError('')
    try {
      const page = await getDocumentsPage({ limit: 50, offset: documents.length })
      setDocuments((current) => [...current, ...page.items])
      setTotalDocuments(page.total)
      setHasMoreDocuments(page.has_more)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch more documents')
    } finally {
      setLoadingMore(false)
    }
  }

  const totalNodes = useMemo(
    () => documents.reduce((sum, doc) => sum + doc.node_count, 0),
    [documents]
  )

  async function handleUpload() {
    if (!selectedFile) {
      setError('Choose a file before uploading')
      return
    }
    setUploading(true)
    setError('')
    setToast('')
    setUploadProgress(10)
    const timer = window.setInterval(() => {
      setUploadProgress((current) => Math.min(90, current + 12))
    }, 180)
    try {
      const doc = await uploadDocument(selectedFile, selectedType)
      setDocuments((current) => [doc, ...current])
      setTotalDocuments((current) => current + 1)
      setToast('Uploaded. MineMind will continue indexing it in the background.')
      setSelectedFile(null)
      setUploadProgress(100)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      window.clearInterval(timer)
      setUploading(false)
    }
  }

  async function handleDelete(datasetName: string) {
    setError('')
    if (!window.confirm('Delete this document memory?')) return
    try {
      await forgetDataset(datasetName)
      setDocuments((current) => current.filter((doc) => doc.dataset_name !== datasetName))
      setTotalDocuments((current) => Math.max(0, current - 1))
      setSelectedDocument((current) => current?.dataset_name === datasetName ? null : current)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  return (
    <motion.main
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="relative min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_50%_10%,rgba(255,255,255,0.12),transparent_28%),linear-gradient(145deg,#000_0%,#070707_46%,#0a0a0a_100%)] px-4 pb-10 pt-24 text-white antialiased sm:px-6 sm:pb-12 sm:pt-28"
      onMouseMove={(event) => {
        const x = event.clientX / window.innerWidth - 0.5
        const y = event.clientY / window.innerHeight - 0.5
        pointerX.set(x)
        pointerY.set(y)
      }}
    >
      <PremiumNav />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_72%,rgba(255,255,255,0.05),transparent_24%),radial-gradient(circle_at_84%_34%,rgba(255,255,255,0.08),transparent_26%)]" />
      <motion.div
        style={{ x: orbX, y: orbY }}
        className="pointer-events-none absolute right-[8%] top-[15%] h-[420px] w-[420px] rounded-full bg-[#bcd7ff]/[0.075] blur-3xl"
      />
      <motion.div
        style={{ x: sheenX, y: sheenY }}
        className="pointer-events-none absolute left-[7%] top-[48%] h-[360px] w-[360px] rounded-full bg-white/[0.045] blur-3xl"
      />

      <motion.header
        variants={itemVariants}
        className="relative z-10 mx-auto max-w-6xl"
      >
        <p className="tracked-label text-[10px] text-white/38">Files</p>
        <div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <h1 className="metal-text text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-6xl">
              Documents
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-white/46">
              Secure repository for incident reports, equipment manuals, and operational knowledge.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-right">
            <div className="rounded-3xl border border-white/10 bg-white/[0.045] px-5 py-4 backdrop-blur-2xl">
              <p className="tracked-label text-[9px] text-white/32">Files</p>
              <p className="mt-2 text-2xl font-semibold text-white/86">{documents.length}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.045] px-5 py-4 backdrop-blur-2xl">
              <p className="tracked-label text-[9px] text-white/32">Indexed sections</p>
              <p className="mt-2 text-2xl font-semibold text-white/86">{totalNodes}</p>
            </div>
          </div>
        </div>
      </motion.header>

      <div className="relative z-10 mx-auto mt-12 grid max-w-6xl gap-8 lg:grid-cols-[0.92fr_1.08fr]">
        <motion.section
          variants={itemVariants}
          className="rounded-[2rem] border border-white/10 bg-white/5 p-4 shadow-[0_0_30px_rgba(255,255,255,0.03),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-xl"
        >
          <motion.div variants={itemVariants}>
            <UploadZone file={selectedFile} onFile={setSelectedFile} />
          </motion.div>

          <motion.button
            type="button"
            onClick={handleUpload}
            disabled={uploading}
            variants={itemVariants}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 360, damping: 18 }}
            className="mt-5 w-full rounded-full bg-neutral-50 px-5 py-4 text-sm font-semibold text-black shadow-[0_0_42px_rgba(255,255,255,0.13)] transition duration-300 hover:bg-white hover:shadow-[0_0_60px_rgba(255,255,255,0.18)] disabled:cursor-not-allowed disabled:opacity-45"
          >
            {uploading ? 'Uploading document...' : 'Add to MineMind Memory'}
          </motion.button>

          {uploading || uploadProgress > 0 ? (
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
              <motion.div
                className="h-full rounded-full bg-white"
                animate={{ width: `${uploadProgress}%` }}
                transition={{ type: 'spring', stiffness: 90, damping: 18 }}
              />
            </div>
          ) : null}
          {toast ? <p className="mt-4 px-1 text-sm text-white/58">{toast}</p> : null}
          {error ? <p className="mt-4 px-1 text-sm text-white/58">{error}</p> : null}
        </motion.section>

        <motion.section
          variants={itemVariants}
          className="min-h-[520px]"
        >
          <div className="mb-5 flex flex-col gap-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="tracked-label text-[10px] text-white/34">Indexed</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white/88">Recent files</h2>
              </div>
              <div className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-white/46 backdrop-blur-xl">
                {documents.length} of {totalDocuments || documents.length} items
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {typeLabels.map((item) => (
                <motion.button
                  key={item.value}
                  type="button"
                  onClick={() => setSelectedType(item.value)}
                  whileHover={{ y: -1 }}
                  whileTap={{ scale: 0.94 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 17 }}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition duration-300 ${
                    selectedType === item.value
                      ? 'border-white/20 bg-gradient-to-b from-neutral-700 to-neutral-800 text-white shadow-[0_0_30px_rgba(255,255,255,0.05)]'
                      : 'border-white/10 bg-white/5 text-neutral-400 hover:border-white/20 hover:text-white'
                  }`}
                >
                  {item.label}
                </motion.button>
              ))}
            </div>
          </div>

          {documents.length === 0 ? (
          <div className="grid min-h-[320px] place-items-center rounded-[2rem] border border-white/10 bg-white/5 p-6 text-center shadow-[0_0_30px_rgba(255,255,255,0.03),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-xl sm:min-h-[420px] sm:p-10">
              <div>
                <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl border border-white/10 bg-white/[0.05] text-white/58">
                  <Layers3 className="h-7 w-7" strokeWidth={1.35} />
                </div>
                <p className="mt-5 text-xl font-semibold text-white/82">No files yet</p>
                <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-white/42">
                  Upload a document to get started.
                </p>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {documents.map((doc, index) => (
                <motion.article
                  key={doc.id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.45, delay: index * 0.035 }}
                  whileHover={{ y: -5, scale: 1.015 }}
                  whileTap={{ scale: 0.985 }}
                  style={{
                    transformStyle: 'preserve-3d'
                  }}
                  className="group relative overflow-hidden rounded-[34px] border border-white/10 bg-[linear-gradient(145deg,rgba(255,255,255,0.068),rgba(255,255,255,0.025))] p-5 shadow-[0_24px_90px_rgba(0,0,0,0.38),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl transition duration-500 hover:border-[#c8dcff]/26 hover:bg-white/[0.075] hover:shadow-[0_34px_120px_rgba(188,215,255,0.09)]"
                >
                  <div className="pointer-events-none absolute inset-0 opacity-0 transition duration-500 group-hover:opacity-100">
                    <div className="absolute -right-16 -top-20 h-44 w-44 rounded-full bg-[#c8dcff]/10 blur-3xl" />
                    <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <div className="relative grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/[0.07] text-white/70 transition group-hover:scale-105 group-hover:bg-white/[0.11] group-hover:text-white">
                      <FileText className="h-5 w-5" strokeWidth={1.45} />
                    </div>
                    <span className="relative rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs text-white/44">
                      {doc.type}
                    </span>
                  </div>

                  <h3 className="relative mt-6 line-clamp-3 min-h-[5.25rem] text-xl font-semibold leading-7 tracking-tight text-white/88">
                    {doc.name}
                  </h3>

                  <div className="relative mt-5 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-white/30">Indexed</p>
                      <p className="mt-1 text-white/64">{formatDate(doc.uploaded_at)}</p>
                    </div>
                    <div>
                      <p className="text-white/30">Indexed sections</p>
                      <p className="mt-1 text-white/64">{doc.node_count}</p>
                    </div>
                  </div>

                  <div className="relative mt-6 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedDocument(doc)}
                      className="flex flex-1 items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-medium text-white/66 transition hover:bg-white hover:text-black hover:shadow-[0_18px_60px_rgba(188,215,255,0.14)]"
                    >
                      <Eye className="h-4 w-4" strokeWidth={1.5} />
                      Preview
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(doc.dataset_name)}
                      className="grid h-11 w-11 place-items-center rounded-2xl border border-white/10 bg-white/[0.035] text-white/42 transition hover:bg-white hover:text-black"
                      aria-label={`Delete ${doc.name}`}
                    >
                      <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                    </button>
                  </div>
                </motion.article>
              ))}
            </div>
          )}
          {hasMoreDocuments ? (
            <button
              type="button"
              onClick={loadMoreDocuments}
              disabled={loadingMore}
              className="mt-6 w-full rounded-full border border-white/10 bg-white/[0.055] px-5 py-3 text-sm font-medium text-white/68 transition hover:border-white/22 hover:bg-white/[0.08] disabled:cursor-wait disabled:opacity-50"
            >
              {loadingMore ? 'Loading more...' : 'Load more files'}
            </button>
          ) : null}
        </motion.section>
      </div>

      <AnimatePresence>
        {selectedDocument ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[70] grid place-items-center bg-black/55 px-6 backdrop-blur-2xl"
            onClick={() => setSelectedDocument(null)}
          >
            <motion.div
              initial={{ opacity: 0, y: 28, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 18, scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 95, damping: 18 }}
              className="w-full max-w-2xl rounded-[40px] border border-white/14 bg-[linear-gradient(145deg,rgba(255,255,255,0.14),rgba(255,255,255,0.045))] p-7 shadow-[0_40px_140px_rgba(0,0,0,0.72),inset_0_1px_0_rgba(255,255,255,0.16)] backdrop-blur-3xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-5">
                <div>
                  <p className="tracked-label text-[10px] text-white/36">Preview</p>
                  <h3 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-white">
                    {selectedDocument.name}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedDocument(null)}
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-white/58 transition hover:bg-white hover:text-black"
                  aria-label="Close preview"
                >
                  <X className="h-5 w-5" strokeWidth={1.5} />
                </button>
              </div>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                {[
                  ['Type', selectedDocument.type],
                  ['Status', selectedDocument.status],
                  ['Indexed sections', String(selectedDocument.node_count)]
                ].map(([label, value]) => (
                  <div key={label} className="rounded-3xl border border-white/10 bg-black/18 p-4">
                    <p className="text-xs text-white/34">{label}</p>
                    <p className="mt-2 text-sm font-medium text-white/78">{value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-3xl border border-white/10 bg-black/20 p-5">
                <p className="text-sm text-white/40">Dataset</p>
                <p className="mt-2 break-all text-sm leading-6 text-white/68">{selectedDocument.dataset_name}</p>
                <p className="mt-5 text-sm text-white/40">Indexed on</p>
                <p className="mt-2 text-sm text-white/68">{formatDate(selectedDocument.uploaded_at)}</p>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.main>
  )
}
