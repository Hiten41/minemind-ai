'use client'

import { motion } from 'framer-motion'
import { FileUp } from 'lucide-react'
import { useDropzone } from 'react-dropzone'

type UploadZoneProps = {
  file: File | null
  onFile: (file: File) => void
}

export default function UploadZone({ file, onFile }: UploadZoneProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt']
    },
    multiple: false,
    onDrop: (acceptedFiles) => {
      const nextFile = acceptedFiles[0]
      if (nextFile) onFile(nextFile)
    }
  })

  const rootProps = getRootProps()

  return (
    <motion.div
      whileHover={{ scale: 1.01 }}
      animate={{ scale: isDragActive ? 0.98 : 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 22 }}
      className={`group relative cursor-pointer overflow-hidden rounded-2xl border p-12 text-center backdrop-blur-xl transition-colors duration-500 ${
        isDragActive
          ? 'border-[#c8dcff]/45 bg-white/10 shadow-[0_0_42px_rgba(200,220,255,0.14),inset_0_0_34px_rgba(255,255,255,0.06)]'
          : 'border-white/10 bg-white/5 shadow-[0_0_30px_rgba(255,255,255,0.03),inset_0_1px_0_rgba(255,255,255,0.1)] hover:border-white/20 hover:bg-white/10'
      }`}
    >
      <div {...rootProps} className="absolute inset-0 z-10">
        <input {...getInputProps()} />
      </div>
      <div className="pointer-events-none absolute inset-0 opacity-0 transition duration-500 group-hover:opacity-100">
        <div className="absolute left-1/2 top-0 h-36 w-72 -translate-x-1/2 rounded-full bg-[#bcd7ff]/10 blur-3xl" />
        <div className="absolute inset-x-10 bottom-0 h-px bg-gradient-to-r from-transparent via-white/24 to-transparent" />
      </div>
      <div className="relative mx-auto grid h-16 w-16 place-items-center rounded-3xl border border-white/12 bg-white/[0.065] text-white/78 shadow-[0_18px_60px_rgba(0,0,0,0.35)] transition duration-500 group-hover:scale-105 group-hover:bg-white/[0.1] group-hover:text-white">
        <FileUp className="h-7 w-7" strokeWidth={1.35} />
      </div>
      <p className="relative mt-6 text-2xl font-semibold tracking-tight text-white">Drop files into memory</p>
      <p className="relative mx-auto mt-2 max-w-sm text-sm leading-6 text-white/42">
        PDF, DOCX, and TXT documents are prepared for MineMind indexing.
      </p>
      <p className="relative mt-5 text-sm font-medium text-white/72">Click to browse</p>
      {file ? (
        <div className="relative mx-auto mt-6 max-w-md rounded-2xl border border-white/10 bg-black/30 px-4 py-3 backdrop-blur-xl">
          <p className="truncate text-sm font-medium text-white/86">{file.name}</p>
          <p className="mt-1 text-xs text-white/38">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
        </div>
      ) : null}
    </motion.div>
  )
}
