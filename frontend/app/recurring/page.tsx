'use client'

import { useEffect, useState } from 'react'
import { api, Recurring } from '@/lib/api'
import { inr, fmtDate } from '@/lib/format'
import { Repeat } from 'lucide-react'

export default function RecurringPage() {
  const [items, setItems] = useState<Recurring[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<Recurring[]>('/recurring').then((r) => { setItems(r); setLoading(false) })
  }, [])

  const activeMonthly = items.filter((i) => i.active).reduce((a, i) => a + i.avg_amount, 0)

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2"><Repeat size={20} /> Recurring & subscriptions</h1>
        <p className="text-muted text-sm">Detected by grouping similar merchants with monthly cadence and stable amounts.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="kpi"><span className="kpi-label">Active recurring</span><span className="kpi-value">{items.filter((i) => i.active).length}</span></div>
        <div className="kpi"><span className="kpi-label">Monthly cost (est.)</span><span className="kpi-value text-red-400">{inr(activeMonthly)}</span></div>
        <div className="kpi"><span className="kpi-label">Annualised</span><span className="kpi-value text-red-400">{inr(activeMonthly * 12)}</span></div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-muted text-xs uppercase bg-surface2/30">
            <tr>
              <th className="text-left table-cell">Merchant</th>
              <th className="text-left table-cell">Category</th>
              <th className="text-right table-cell">Avg amount</th>
              <th className="text-right table-cell">Cadence</th>
              <th className="text-right table-cell">Volatility</th>
              <th className="text-left table-cell">Last seen</th>
              <th className="text-left table-cell">Next est.</th>
              <th className="text-left table-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="table-cell text-center text-muted py-8">Scanning…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8} className="table-cell text-center text-muted py-8">No recurring patterns detected yet. Need at least 3 similar transactions roughly a month apart.</td></tr>
            ) : items.map((r) => (
              <tr key={r.key} className="border-t border-border">
                <td className="table-cell font-medium">{r.merchant}</td>
                <td className="table-cell text-muted">{r.category_name || '—'}</td>
                <td className="table-cell text-right font-mono text-red-400">{inr(r.avg_amount)}</td>
                <td className="table-cell text-right">{r.avg_cadence_days}d</td>
                <td className="table-cell text-right">{r.amount_volatility_pct.toFixed?.(1) ?? r.amount_volatility_pct}%</td>
                <td className="table-cell text-muted">{fmtDate(r.last_seen)}</td>
                <td className="table-cell">{fmtDate(r.next_estimated)}</td>
                <td className="table-cell">
                  {r.active
                    ? <span className="chip text-emerald-400" style={{ borderColor: '#10b981' }}>active</span>
                    : <span className="chip text-muted">paused</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
