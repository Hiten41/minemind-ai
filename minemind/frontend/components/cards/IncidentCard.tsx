export type Incident = {
  id: string
  title: string
  date: string
  severity: 'High' | 'Medium' | 'Low'
  status: 'Open' | 'Resolved'
  equipment: string
}

type IncidentCardProps = Incident & {
  onClick: () => void
  isSelected: boolean
}

const severityClass: Record<Incident['severity'], string> = {
  High: 'bg-danger/15 text-danger',
  Medium: 'bg-white/10 text-white/68',
  Low: 'bg-success/15 text-success'
}

const statusClass: Record<Incident['status'], string> = {
  Open: 'bg-danger/15 text-danger',
  Resolved: 'bg-success/15 text-success'
}

export default function IncidentCard({
  id,
  title,
  date,
  severity,
  status,
  equipment,
  onClick,
  isSelected
}: IncidentCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border bg-card p-4 text-left transition hover:border-white/30 ${
        isSelected ? 'border-white/35' : 'border-card-border'
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-[#888888]">{id} - {date}</p>
          <h2 className="mt-1 font-semibold text-white">{title}</h2>
        </div>
        <span className={`rounded px-2 py-1 text-xs font-medium ${severityClass[severity]}`}>
          {severity}
        </span>
      </div>
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="truncate text-[#888888]">{equipment}</span>
        <span className={`rounded px-2 py-1 text-xs font-medium ${statusClass[status]}`}>
          {status}
        </span>
      </div>
    </button>
  )
}
