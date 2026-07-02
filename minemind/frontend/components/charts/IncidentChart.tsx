'use client'

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

type IncidentPoint = {
  month: string
  count: number
}

export default function IncidentChart({ data }: { data: IncidentPoint[] }) {
  return (
    <div className="h-80 rounded-xl border border-card-border bg-card p-6">
      <h2 className="text-lg font-semibold text-white">Incidents Per Month</h2>
      <p className="mb-6 text-sm text-[#888888]">Monthly safety events recorded in memory</p>
      <ResponsiveContainer width="100%" height="80%">
        <BarChart data={data}>
          <CartesianGrid stroke="#1f1f1f" />
          <XAxis dataKey="month" stroke="#888888" />
          <YAxis stroke="#888888" />
          <Tooltip
            cursor={{ fill: '#1a1a1a' }}
            contentStyle={{ background: '#111111', border: '1px solid #1f1f1f', color: '#ffffff' }}
          />
          <Bar dataKey="count" fill="#ef4444" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
