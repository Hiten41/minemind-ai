export type Equipment = {
  id: string
  name: string
  status: 'Active' | 'Maintenance' | 'Offline'
  risk: 'Low' | 'Medium' | 'High'
  incidents: number
  lastInspection: string
}

type EquipmentCardProps = Equipment & {
  onClick: () => void
  isSelected: boolean
}

const statusClass: Record<Equipment['status'], string> = {
  Active: 'bg-success/15 text-success',
  Maintenance: 'bg-white/10 text-white/72',
  Offline: 'bg-danger/15 text-danger'
}

const riskClass: Record<Equipment['risk'], string> = {
  Low: 'text-success',
  Medium: 'text-white/72',
  High: 'text-danger'
}

export default function EquipmentCard({
  id,
  name,
  status,
  risk,
  incidents,
  lastInspection,
  onClick,
  isSelected
}: EquipmentCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-w-0 rounded-xl border bg-card p-5 text-left transition hover:border-white/40 sm:p-6 ${
        isSelected ? 'border-white/60' : 'border-card-border'
      }`}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs text-[#888888]">{id}</p>
          <h2 className="mt-1 break-words text-lg font-semibold text-white">{name}</h2>
        </div>
        <span className={`shrink-0 rounded px-2 py-1 text-xs font-medium ${statusClass[status]}`}>
          {status}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 text-sm min-[420px]:grid-cols-3">
        <div>
          <p className="text-[#888888]">Risk</p>
          <p className={`font-semibold ${riskClass[risk]}`}>{risk}</p>
        </div>
        <div>
          <p className="text-[#888888]">Incidents</p>
          <p className="font-semibold text-white">{incidents}</p>
        </div>
        <div>
          <p className="text-[#888888]">Inspection</p>
          <p className="break-words font-semibold text-white">{lastInspection}</p>
        </div>
      </div>
    </button>
  )
}
