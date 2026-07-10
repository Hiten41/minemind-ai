'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import EquipmentCard, { type Equipment } from '@/components/cards/EquipmentCard'
import PremiumNav from '@/components/experience/PremiumNav'
import { getDocumentIntelligence, getGraphData } from '@/lib/api'
import type { DocumentIntelligence, DocumentIntelligenceItem, GraphNode } from '@/types'

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
  return dateMatch?.[0] ?? 'Recorded in your uploaded documents'
}

const riskRank: Record<Equipment['risk'], number> = {
  Low: 0,
  Medium: 1,
  High: 2
}

const statusRank: Record<Equipment['status'], number> = {
  Active: 0,
  Maintenance: 1,
  Offline: 2
}

function equipmentKey(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
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

function mergeEquipmentItems(items: Equipment[]): Equipment[] {
  const merged = new Map<string, Equipment>()

  for (const item of items) {
    const key = equipmentKey(item.name)
    if (!key) continue
    const existing = merged.get(key)

    if (!existing) {
      merged.set(key, item)
      continue
    }

    merged.set(key, {
      ...existing,
      id: existing.id,
      name: existing.name.length >= item.name.length ? existing.name : item.name,
      status: statusRank[item.status] > statusRank[existing.status] ? item.status : existing.status,
      risk: riskRank[item.risk] > riskRank[existing.risk] ? item.risk : existing.risk,
      incidents: Math.min(99, existing.incidents + item.incidents),
      lastInspection: existing.lastInspection.includes('uploaded documents') ? item.lastInspection : existing.lastInspection
    })
  }

  return Array.from(merged.values()).sort((a, b) => (
    riskRank[b.risk] - riskRank[a.risk] ||
    b.incidents - a.incidents ||
    a.name.localeCompare(b.name)
  ))
}

function graphWithTimeout() {
  return Promise.race([
    getGraphData(),
    new Promise<{ nodes: GraphNode[]; edges: [] }>((resolve) => {
      window.setTimeout(() => resolve({ nodes: [], edges: [] }), 8000)
    })
  ])
}

function documentIntelligenceWithTimeout() {
  return Promise.race([
    getDocumentIntelligence(),
    new Promise<DocumentIntelligence>((resolve) => {
      window.setTimeout(() => resolve({ documents: [], top_entities: [] }), 8000)
    })
  ])
}

function EquipmentDetails({
  equipment,
  onClose,
  onAsk
}: {
  equipment: Equipment
  onClose: () => void
  onAsk: () => void
}) {
  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-[#888888]">{equipment.id}</p>
          <h2 className="mt-1 break-words text-xl font-semibold text-white">{equipment.name}</h2>
        </div>
        <button type="button" onClick={onClose} className="min-h-11 shrink-0 rounded-full px-3 text-[#888888] hover:text-white">
          Close
        </button>
      </div>
      <div className="mt-6 space-y-4 text-sm">
        <p><span className="text-[#888888]">Status:</span> <span className="text-white">{equipment.status}</span></p>
        <p><span className="text-[#888888]">Risk:</span> <span className="text-white">{equipment.risk}</span></p>
        <p><span className="text-[#888888]">Last inspection:</span> <span className="text-white">{equipment.lastInspection}</span></p>
        <p><span className="text-[#888888]">Incidents:</span> <span className="text-white">{equipment.incidents}</span></p>
      </div>
      <button
        type="button"
        onPointerDown={onAsk}
        onClick={onAsk}
        className="mt-8 min-h-11 w-full rounded-lg border border-white/15 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/15"
      >
        Ask AI About This Equipment
      </button>
    </div>
  )
}

export default function EquipmentPage() {
  const router = useRouter()
  const [items, setItems] = useState<Equipment[]>([])
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    Promise.all([graphWithTimeout(), documentIntelligenceWithTimeout()])
      .then(([graph, intelligence]) => {
        if (cancelled) return
        const equipmentNodes = graph.nodes.filter((node) => node.type === 'equipment')
        const nextItems = mergeEquipmentItems([
          ...equipmentNodes.map(nodeToEquipment),
          ...documentEquipmentItems(intelligence.documents)
        ])
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
    if (loading) return 'Loading equipment from your uploaded documents...'
    if (error) return error
    return "No equipment found yet. Upload a maintenance report or incident report that mentions specific machinery, and it'll show up here."
  }, [error, loading])

  function askAboutEquipment(equipment: Equipment) {
    router.push(`/chat?q=${encodeURIComponent(`Tell me about ${equipment.name} maintenance history and any associated incidents or safety concerns`)}`)
  }

  return (
    <main className="premium-bg min-h-screen overflow-x-hidden pt-20 text-white sm:pt-24">
      <PremiumNav />
      <div className={`grid min-h-[calc(100dvh-5rem)] grid-cols-1 gap-5 p-4 sm:p-6 lg:h-[calc(100vh-6rem)] lg:gap-6 lg:overflow-hidden lg:p-8 ${
        selectedEquipment ? 'lg:grid-cols-[minmax(0,1fr)_360px]' : ''
      }`}>
        <div className="grid auto-rows-max grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 lg:gap-6 lg:overflow-auto">
          {items.length > 0 ? items.map((item) => (
            <div key={item.id} className="contents">
              <EquipmentCard
                {...item}
                isSelected={selectedEquipment?.id === item.id}
                onClick={() => setSelectedEquipment(item)}
              />
              {selectedEquipment?.id === item.id ? (
                <div className="rounded-xl border border-card-border bg-card p-5 sm:col-span-2 sm:p-6 lg:hidden">
                  <EquipmentDetails
                    equipment={selectedEquipment}
                    onClose={() => setSelectedEquipment(null)}
                    onAsk={() => askAboutEquipment(selectedEquipment)}
                  />
                </div>
              ) : null}
            </div>
          )) : (
            <div className="min-w-0 rounded-xl border border-card-border bg-card p-6 text-[#888888] sm:col-span-2">
              <p className="max-w-4xl whitespace-normal text-balance leading-7">{emptyLabel}</p>
              {!loading && !error ? (
                <button
                  type="button"
                  onClick={() => router.push('/documents')}
                  className="mt-4 min-h-11 rounded-lg border border-white/15 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/15"
                >
                  Upload a document
                </button>
              ) : null}
            </div>
          )}
        </div>
        {selectedEquipment ? (
          <aside className="hidden rounded-xl border border-card-border bg-card p-5 sm:p-6 lg:block lg:h-fit">
            <EquipmentDetails
              equipment={selectedEquipment}
              onClose={() => setSelectedEquipment(null)}
              onAsk={() => askAboutEquipment(selectedEquipment)}
            />
          </aside>
        ) : null}
      </div>
    </main>
  )
}
