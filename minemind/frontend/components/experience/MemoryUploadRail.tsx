'use client'

import { motion } from 'framer-motion'
import { Check, FileUp, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useDropzone } from 'react-dropzone'

import { uploadDocument } from '@/lib/api'
import type { Document } from '@/types'

export default function MemoryUploadRail({
  onUploadComplete
}: {
  onUploadComplete?: (document: Document) => void
}) {
  const [state, setState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('Drop incident PDFs into MineMind Memory')

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt']
    },
    multiple: false,
    onDrop: async (acceptedFiles) => {
      const file = acceptedFiles[0]
      if (!file) return
      setState('uploading')
      setMessage(file.name)
      try {
        const doc = await uploadDocument(file, 'incident')
        setState('done')
        setMessage(`${doc.node_count} memory nodes created`)
        onUploadComplete?.(doc)
        window.setTimeout(() => {
          setState('idle')
          setMessage('Drop incident PDFs into MineMind Memory')
        }, 2600)
      } catch (error) {
        setState('error')
        setMessage(error instanceof Error ? error.message : 'Upload failed')
      }
    }
  })

  return (
    <motion.aside
      initial={{ x: -52, opacity: 0.36 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 70, damping: 18, delay: 0.35 }}
      className="group fixed left-5 top-1/2 z-40 -translate-y-1/2"
    >
      <div
        {...getRootProps()}
        className={`glass-depth-subtle w-[74px] cursor-pointer overflow-hidden rounded-[28px] px-4 py-5 transition-all duration-500 group-hover:w-[320px] ${
          isDragActive ? 'amber-aura bg-white/10' : ''
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex items-center gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-white/[0.08] text-[#d7b779] shadow-[inset_0_1px_0_rgba(255,255,255,0.16)]">
            {state === 'uploading' ? (
              <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
            ) : state === 'done' ? (
              <Check className="h-5 w-5" strokeWidth={1.7} />
            ) : (
              <FileUp className="h-5 w-5" strokeWidth={1.5} />
            )}
          </div>
          <div className="min-w-0 opacity-0 transition duration-300 group-hover:opacity-100">
            <p className="tracked-label text-[10px] text-white/42">Memory Intake</p>
            <p className={`mt-2 truncate text-sm ${state === 'error' ? 'text-[#d6a6a6]' : 'text-white/76'}`}>
              {message}
            </p>
            <p className="mt-1 text-xs text-white/34">PDF, DOCX, TXT</p>
          </div>
        </div>
      </div>
    </motion.aside>
  )
}
