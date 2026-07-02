'use client'

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip
} from 'recharts'

type DocumentTypePoint = {
  name: string
  value: number
}

const colors = ['#3b82f6', '#10b981', '#ef4444', '#8b5cf6', '#f59e0b']

export default function MaintenanceChart({ data }: { data: DocumentTypePoint[] }) {
  const chartData = data.length > 0 ? data : [{ name: 'No documents', value: 1 }]

  return (
    <div className="h-80 rounded-xl border border-card-border bg-card p-6">
      <h2 className="text-lg font-semibold text-white">Document Types</h2>
      <p className="mb-6 text-sm text-[#888888]">Memory distribution by uploaded source type</p>
      <ResponsiveContainer width="100%" height="80%">
        <PieChart>
          <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={90}>
            {chartData.map((entry, index) => (
              <Cell key={entry.name} fill={data.length > 0 ? colors[index % colors.length] : '#333333'} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: '#111111', border: '1px solid #1f1f1f', color: '#ffffff' }} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
