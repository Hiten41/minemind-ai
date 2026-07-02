'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import EquipmentCard, { type Equipment } from '@/components/cards/EquipmentCard'
import BackToDashboard from '@/components/experience/BackToDashboard'
import PremiumNav from '@/components/experience/PremiumNav'
import { getDocumentIntelligence, getGraphData } from '@/lib/api'
import type { DocumentIntelligenceItem, GraphNode } from '@/types'

function deriveStatus(text: string): Equipment['status'] {
  const lowered = text.toLowerCase()
  if (/(offline|shutdown|out of service|failed)/.test(lowered)) return 'Offline'
  if (/(maintenance|service|repair|inspection)/.test(lowered)) return 'Maintenance'
  return 'Active'
}

function deriveRisk(text: string): Equipment['risk'] {
  const lowered = text.toLowerCase()
  if (/(hazard|failure|incident|unsafe|critical|leak|fault|breakdown)/.test(lowered)) return 'High'
  if (/(maintenance|inspection|wear|warning|issue|replace)/.test(lowered)) return 'Medium'
  return 'Low'
}

function deriveIncidents(text: string): number {
  const matches = text.match(/incident|failure|fault|alarm|shutdown|repair|maintenance/gi)
  return Math.min(9, matches?.length ?? 0)
}

function deriveLastInspection(text: string): string {
  const dateMatch = text.match(/\b\d{4}-\d{2}-\d{2}\b|\b\d{2}\/\d{2}\/\d{4}\b/)
  return dateMatch?.[0] ?? 'Recorded in memory graph'
}

function nodeToEquipment(node: GraphNode): Equipment {
  const fullText = `${node.label} ${node.data.full_text ?? ''}`.trim()
  return {
    id: node.id.toUpperCase(),
    name: node.label || `Equipment ${node.id}`,
    status: deriveStatus(fullText),
    risk: deriveRisk(fullText),
    incidents: deriveIncidents(fullText),
    lastInspection: deriveLastInspection(fullText)
  }
}

function documentEquipmentItems(documents: DocumentIntelligenceItem[]): Equipment[] {
  const items = new Map<string, Equipment>()

  for (const document of documents) {
    for (const equipment of document.signals.equipment) {
      const key = equipment.toLowerCase()
      const summary = `${equipment} ${document.summary}`
      const existing = items.get(key)
      items.set(key, {
        id: existing?.id ?? `EQ-${items.size + 1}`,
        name: equipment.charAt(0).toUpperCase() + equipment.slice(1),
        status: deriveStatus(summary),
        risk: deriveRisk(summary),
        incidents: (existing?.incidents ?? 0) + deriveIncidents(summary),
        lastInspection: existing?.lastInspection ?? `Found in ${document.name}`,
      })
    }
  }

  return Array.from(items.values())
}

function graphWithTimeout() {
  return Promise.race([
    getGraphData(),
    new Promise<{ nodes: GraphNode[]; edges: [] }>((resolve) => {
      window.setTimeout(() => resolve({ nodes: [], edges: [] }), 8000)
    })
  ])
}

export default function EquipmentPage() {
  const router = useRouter()
  const [items, setItems] = useState<Equipment[]>([])
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    Promise.all([graphWithTimeout(), getDocumentIntelligence()])
      .then(([graph, intelligence]) => {
        if (cancelled) return
        const equipmentNodes = graph.nodes.filter((node) => node.type === 'equipment')
        const nextItems = equipmentNodes.length > 0
          ? equipmentNodes.map(nodeToEquipment)
          : documentEquipmentItems(intelligence.documents)
        setItems(nextItems)
        setSelectedEquipment((current) => {
          if (!current) return current
          return nextItems.find((item) => item.id === current.id) ?? null
        })
        setError('')
      })
      .catch(() => {
        if (!cancelled) setError('Equipment data could not be loaded right now.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const emptyLabel = useMemo(() => {
    if (loading) return 'Loading equipment from the memory graph...'
    if (error) return error
    return 'No equipment nodes were found in the current memory graph.'
  }, [error, loading])

  return (
    <main className="premium-bg min-h-screen overflow-x-hidden pt-20 text-white sm:pt-24">
      <PremiumNav />
      <BackToDashboard />
      <div className="grid min-h-[calc(100dvh-5rem)] grid-cols-1 gap-5 p-4 sm:p-6 lg:h-[calc(100vh-6rem)] lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-6 lg:overflow-hidden lg:p-8">
        <div className="grid auto-rows-max grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 lg:gap-6 lg:overflow-auto">
          {items.length > 0 ? items.map((item) => (
            <EquipmentCard
              key={item.id}
              {...item}
              isSelected={selectedEquipment?.id === item.id}
              onClick={() => setSelectedEquipment(item)}
            />
          )) : (
            <div className="rounded-xl border border-card-border bg-card p-6 text-[#888888] sm:col-span-2">
              {emptyLabel}
            </div>
          )}
        </div>
        <aside className="rounded-xl border border-card-border bg-card p-5 sm:p-6 lg:h-fit">
          {selectedEquipment ? (
            <div>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-[#888888]">{selectedEquipment.id}</p>
                  <h2 className="mt-1 text-xl font-semibold text-white">{selectedEquipment.name}</h2>
                </div>
                <button type="button" onClick={() => setSelectedEquipment(null)} className="text-[#888888] hover:text-white">
                  Close
                </button>
              </div>
              <div className="mt-6 space-y-4 text-sm">
                <p><span className="text-[#888888]">Status:</span> <span className="text-white">{selectedEquipment.status}</span></p>
                <p><span className="text-[#888888]">Risk:</span> <span className="text-white">{selectedEquipment.risk}</span></p>
                <p><span className="text-[#888888]">Last inspection:</span> <span className="text-white">{selectedEquipment.lastInspection}</span></p>
                <p><span className="text-[#888888]">Incidents:</span> <span className="text-white">{selectedEquipment.incidents}</span></p>
              </div>
              <button
                type="button"
                onPointerDown={() => router.push(`/chat?q=${encodeURIComponent(`Tell me about ${selectedEquipment.name} maintenance history and any associated incidents or safety concerns`)}`)}
                onClick={() => router.push(`/chat?q=${encodeURIComponent(`Tell me about ${selectedEquipment.name} maintenance history and any associated incidents or safety concerns`)}`)}
                className="mt-8 w-full rounded-lg border border-white/15 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/15"
              >
                Ask AI About This Equipment
              </button>
            </div>
          ) : loading ? (
            <p className="text-[#888888]">Loading equipment from the memory graph...</p>
          ) : error ? (
            <p className="text-[#888888]">{error}</p>
          ) : (
            <p className="text-[#888888]">Select equipment to inspect maintenance and incident context.</p>
          )}
        </aside>
      </div>
    </main>
  )
}
