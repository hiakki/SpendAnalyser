'use client'

import { useEffect, useState } from 'react'
import { api, Anomaly } from '@/lib/api'
import { inr, fmtDate } from '@/lib/format'
import { AlertTriangle } from 'lucide-react'

export default function AnomaliesPage() {
  const [items, setItems] = useState<Anomaly[]>([])
  const [threshold, setThreshold] = useState(2.5)
  const [minAmount, setMinAmount] = useState(500)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get<Anomaly[]>('/anomalies', { z_threshold: threshold, min_amount: minAmount })
      .then((r) => { setItems(r); setLoading(false) })
  }, [threshold, minAmount])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2"><AlertTriangle size={20} className="text-amber-400" /> Anomalies</h1>
        <p className="text-muted text-sm">Per-category z-score: transactions much larger than your usual spend in that category.</p>
      </div>

      <div className="card flex flex-wrap gap-4 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">z-score threshold</label>
          <input type="number" step="0.1" className="input w-32" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value) || 2.5)} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">Min amount (₹)</label>
          <input type="number" step="100" className="input w-32" value={minAmount} onChange={(e) => setMinAmount(parseFloat(e.target.value) || 0)} />
        </div>
        <div className="text-xs text-muted">{loading ? 'Scanning…' : `${items.length} flagged`}</div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-muted text-xs uppercase bg-surface2/30">
            <tr>
              <th className="text-left table-cell">Date</th>
              <th className="text-left table-cell">Description</th>
              <th className="text-left table-cell">Category</th>
              <th className="text-right table-cell">Amount</th>
              <th className="text-right table-cell">Category avg</th>
              <th className="text-right table-cell">z-score</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading ? (
              <tr><td colSpan={6} className="table-cell text-center text-muted py-8">No anomalies above the current threshold.</td></tr>
            ) : items.map((a) => (
              <tr key={a.transaction_id} className="border-t border-border">
                <td className="table-cell text-muted whitespace-nowrap">{fmtDate(a.posted_at)}</td>
                <td className="table-cell max-w-[360px] truncate" title={a.description}>{a.merchant || a.description}</td>
                <td className="table-cell">{a.category_name}</td>
                <td className="table-cell text-right font-mono text-red-400">{inr(a.amount)}</td>
                <td className="table-cell text-right font-mono text-muted">{inr(a.category_mean)}</td>
                <td className="table-cell text-right font-mono text-amber-400">{a.z_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
