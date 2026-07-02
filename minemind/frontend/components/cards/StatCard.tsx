type StatCardProps = {
  label: string
  value: number
  color: string
  icon: string
}

export default function StatCard({ label, value, color, icon }: StatCardProps) {
  return (
    <div
      className="rounded-xl border border-card-border bg-card p-6 transition hover:border-gold"
      style={{ borderTopColor: color, borderTopWidth: 3 }}
    >
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-[#888888]">{label}</span>
        <span className="rounded bg-background px-2 py-1 text-xs font-semibold" style={{ color }}>
          {icon}
        </span>
      </div>
      <div className="text-4xl font-bold text-white">{value}</div>
    </div>
  )
}
