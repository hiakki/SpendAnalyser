'use client'

import { useEffect, useState } from 'react'
import { api, BudgetStatus, Category } from '@/lib/api'
import { inr } from '@/lib/format'
import { Save } from 'lucide-react'

function currentMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function BudgetsPage() {
  const [month, setMonth] = useState(currentMonth())
  const [status, setStatus] = useState<BudgetStatus[]>([])
  const [cats, setCats] = useState<Category[]>([])
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [recurring, setRecurring] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  async function refresh() {
    setError(null)
    try {
    const [s, c] = await Promise.all([
      api.get<BudgetStatus[]>('/budgets/status', { month }),
      api.get<Category[]>('/categories'),
    ])
    setStatus(s); setCats(c)
    const d: Record<number, string> = {}
    s.forEach((r) => { d[r.category_id] = String(r.budget || '') })
    setDrafts(d)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load budgets. Please try again.') }
  }

  useEffect(() => { refresh() }, [month])

  async function save(cat_id: number) {
    const v = parseFloat(drafts[cat_id] || '0')
    if (!Number.isFinite(v) || v < 0) { setError('Enter a valid budget of zero or more.'); return }
    setSaving(cat_id)
    setError(null)
    try {
      await api.post('/budgets', { category_id: cat_id, month: recurring ? '*' : month, amount: v })
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save this budget. Please try again.') }
    finally { setSaving(null) }
  }

  const allCats = cats
    .filter((c) => !status.some((s) => s.category_id === c.id))
    .map((c) => ({
      category_id: c.id, category_name: c.name, color: c.color,
      budget: 0, actual: 0, remaining: 0, percent: 0, over: false,
    } as BudgetStatus))

  const rows = [...status, ...allCats]
  const totalBudget = rows.reduce((a, r) => a + r.budget, 0)
  const totalActual = rows.reduce((a, r) => a + r.actual, 0)

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Budgets</h1>
          <p className="text-muted text-sm">Set monthly budgets per category. Use <span className="chip">recurring</span> to apply the same amount every month.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <label htmlFor="budget-month" className="text-sm text-muted">Month</label>
          <input id="budget-month" type="month" className="input" value={month} onChange={(e) => setMonth(e.target.value)} />
          <label className="flex items-center gap-2 text-sm text-muted ml-4">
            <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} /> Recurring
          </label>
        </div>
      </div>

      {error ? <div role="alert" className="notice text-red-400">{error} <button className="btn btn-ghost" onClick={refresh}>Retry loading</button></div> : null}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="kpi"><span className="kpi-label">Total budget</span><span className="kpi-value">{inr(totalBudget)}</span></div>
        <div className="kpi"><span className="kpi-label">Categorized outflow ({month})</span><span className="kpi-value text-red-400">{inr(totalActual)}</span></div>
        <div className="kpi"><span className="kpi-label">Remaining</span><span className={`kpi-value ${(totalBudget - totalActual) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{inr(totalBudget - totalActual)}</span></div>
      </div>

      <p className="text-xs text-muted">Outflow includes every categorized debit, with or without a budget, including transfers and card repayments. Uncategorized rows are excluded. Remaining is your total budget minus this outflow.</p>
      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted text-xs uppercase bg-surface2/30">
            <tr>
              <th className="text-left table-cell">Category</th>
              <th className="text-right table-cell">Budget (₹)</th>
              <th className="text-right table-cell">Outflow</th>
              <th className="text-right table-cell">Remaining</th>
              <th className="table-cell">Progress</th>
              <th className="table-cell"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pct = r.budget ? Math.min(100, (r.actual / r.budget) * 100) : 0
              const over = r.budget && r.actual > r.budget
              return (
                <tr key={r.category_id} className="border-t border-border">
                  <td className="table-cell">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: r.color || '#64748b' }} />
                      {r.category_name}
                    </span>
                  </td>
                  <td className="table-cell text-right">
                    <input
                      type="number"
                      aria-label={`Budget for ${r.category_name}`}
                      min="0"
                      step="100"
                      className="input w-32 text-right py-1"
                      value={drafts[r.category_id] ?? ''}
                      onChange={(e) => setDrafts((d) => ({ ...d, [r.category_id]: e.target.value }))}
                    />
                  </td>
                  <td className="table-cell text-right font-mono">{inr(r.actual)}</td>
                  <td className={`table-cell text-right font-mono ${over ? 'text-red-400' : 'text-emerald-400'}`}>
                    {inr(r.budget - r.actual)}
                  </td>
                  <td className="table-cell w-64">
                    <div className="h-2 bg-surface2 rounded">
                      <div
                        className={`h-2 rounded ${over ? 'bg-red-500' : 'bg-cyan-500'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-muted mt-1">{r.budget ? `${r.percent}%` : '—'}</div>
                  </td>
                  <td className="table-cell text-right">
                    <button aria-label={`Save budget for ${r.category_name}`} disabled={saving !== null} className="btn btn-ghost text-xs" onClick={() => save(r.category_id)}>
                      <Save size={14} /> {saving === r.category_id ? 'Saving…' : 'Save'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
