'use client'

import { useEffect, useState } from 'react'
import { api, Account, Category, Rule } from '@/lib/api'
import { Plus, Trash2, RotateCcw, Sparkles, Zap, Tag, FolderPlus } from 'lucide-react'

export default function SettingsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [cats, setCats] = useState<Category[]>([])
  const [rules, setRules] = useState<Rule[]>([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string>('')

  const [np, setNp] = useState({ pattern: '', category_id: 0, priority: 50 })

  async function refresh() {
    const [a, c, r] = await Promise.all([api.get<Account[]>('/accounts'), api.get<Category[]>('/categories'), api.get<Rule[]>('/rules')])
    setAccounts(a); setCats(c); setRules(r)
    if (c[0] && np.category_id === 0) setNp((x) => ({ ...x, category_id: c[0].id }))
  }

  useEffect(() => { refresh() }, [])

  async function addRule() {
    if (!np.pattern || !np.category_id) return
    await api.post('/rules', { pattern: np.pattern, is_regex: false, category_id: np.category_id, priority: np.priority })
    setNp({ pattern: '', category_id: np.category_id, priority: np.priority })
    await refresh()
  }

  async function recategorize() {
    setBusy(true)
    try {
      const r = await api.post<{ changed: number }>('/rules/recategorize', null)
      setMsg(`Re-categorized ${r.changed} transactions.`)
    } finally { setBusy(false) }
  }

  async function reset() {
    if (!confirm('Wipe ALL data (accounts, statements, transactions, budgets)? This cannot be undone.')) return
    await api.post('/admin/reset', null)
    setMsg('Database reset.')
    await refresh()
  }

  async function seedMock() {
    setBusy(true)
    try {
      const r = await api.post<{ inserted: number }>('/admin/seed-mock', null)
      setMsg(`Inserted ${r.inserted} mock transactions.`)
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-muted text-sm">Rules, accounts, and database utilities.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card lg:col-span-1">
          <h3 className="font-medium mb-2">Accounts</h3>
          <ul className="space-y-2">
            {accounts.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 border-b border-border pb-2">
                <div>
                  <div className="text-sm">{a.name}</div>
                  <div className="text-xs text-muted">{a.kind} · {a.institution || '—'}</div>
                </div>
                <button className="btn btn-ghost text-red-400" onClick={async () => {
                  if (!confirm(`Delete account "${a.name}" and ALL its transactions?`)) return
                  await api.del(`/accounts/${a.id}`); await refresh()
                }}><Trash2 size={14} /></button>
              </li>
            ))}
            {accounts.length === 0 ? <li className="text-sm text-muted">No accounts yet.</li> : null}
          </ul>
        </div>

        <div className="card lg:col-span-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Categorization rules</h3>
            <button className="btn" disabled={busy} onClick={recategorize}><Sparkles size={14} /> Re-categorize all</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end mb-3">
            <div className="md:col-span-2 flex flex-col gap-1">
              <label className="text-xs text-muted">Pattern (substring)</label>
              <input className="input" value={np.pattern} onChange={(e) => setNp({ ...np, pattern: e.target.value })} placeholder="e.g. amazon, zomato, neft-rent" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Category</label>
              <select className="input" value={np.category_id} onChange={(e) => setNp({ ...np, category_id: Number(e.target.value) })}>
                {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Priority (lower=stronger)</label>
              <input type="number" className="input" value={np.priority} onChange={(e) => setNp({ ...np, priority: parseInt(e.target.value) || 50 })} />
            </div>
            <button className="btn btn-primary" onClick={addRule}><Plus size={14} /> Add</button>
          </div>

          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="text-muted text-xs uppercase">
                <tr>
                  <th className="text-left table-cell">Pattern</th>
                  <th className="text-left table-cell">Category</th>
                  <th className="text-right table-cell">Priority</th>
                  <th className="table-cell"></th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="table-cell font-mono text-xs">{r.pattern}{r.is_regex ? ' (regex)' : ''}</td>
                    <td className="table-cell">{cats.find((c) => c.id === r.category_id)?.name || '?'}</td>
                    <td className="table-cell text-right">{r.priority}</td>
                    <td className="table-cell text-right">
                      <button className="btn btn-ghost text-red-400" onClick={async () => { await api.del(`/rules/${r.id}`); await refresh() }}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="font-medium mb-2">Utilities</h3>
        <div className="flex flex-wrap gap-2">
          <button className="btn" disabled={busy} onClick={async () => {
            const r = await api.post<{ created: string[]; skipped: string[] }>('/admin/quick-setup', null)
            setMsg(`Created ${r.created.length} accounts${r.skipped.length ? ` (${r.skipped.length} already existed)` : ''}.`)
            await refresh()
          }}>
            <Zap size={14} /> Create common accounts
          </button>
          <button className="btn" disabled={busy} onClick={async () => {
            setBusy(true)
            try {
              const r = await api.post<{ transactions_scanned: number; merchants_updated: number; user_labels_set: number; categories_changed: number }>('/admin/reparse-merchants', null)
              setMsg(`Scanned ${r.transactions_scanned} · merchants updated: ${r.merchants_updated} · UPI labels extracted: ${r.user_labels_set} · categories changed: ${r.categories_changed}.`)
            } finally { setBusy(false) }
          }} title="Re-extract merchants and UPI labels from existing transactions and re-categorize">
            <Tag size={14} /> Re-extract UPI labels & re-categorize
          </button>
          <button className="btn" disabled={busy} onClick={async () => {
            setBusy(true)
            try {
              const r = await api.post<{ created_categories: { name: string; transactions: number }[]; reassigned: number; loan_assigned: number; skipped: number }>('/admin/auto-grow', null)
              const created = r.created_categories.map((c) => `${c.name} (${c.transactions})`).join(', ')
              setMsg(
                `Created ${r.created_categories.length} categories${created ? `: ${created}` : ''} · ` +
                `reassigned ${r.reassigned} · ${r.loan_assigned} → Loan Given · ${r.skipped} stayed in Other.`,
              )
              await refresh()
            } finally { setBusy(false) }
          }} title="Create categories for repeated merchant patterns in Other. Review suggested classifications against your statements.">
            <FolderPlus size={14} /> Auto-grow categories from Other
          </button>
          <button className="btn" disabled={busy} onClick={seedMock}><Sparkles size={14} /> Generate 6 months of demo data</button>
          <button className="btn text-red-400" disabled={busy} onClick={reset}><RotateCcw size={14} /> Reset database</button>
        </div>
        {msg ? <div className="text-emerald-400 text-sm mt-2">{msg}</div> : null}
      </div>
    </div>
  )
}
