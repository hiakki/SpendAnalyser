'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, Account, Category, Transaction, Summary } from '@/lib/api'
import { inr2 as inr, fmtDate } from '@/lib/format'
import { Search, Download, Filter, AlertTriangle, Tags, CheckCircle2 } from 'lucide-react'

function sourceLabel(source?: string) {
  if (!source) return null
  if (source === 'upi_label') return 'Bank note'
  if (source === 'label_review') return 'Needs review'
  if (source === 'user') return 'Manual'
  if (source === 'rule') return 'Rule'
  if (source === 'llm') return 'LLM'
  if (source === 'auto') return 'Auto'
  if (source === 'auto-human') return 'Auto'
  return source
}

export default function TransactionsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [items, setItems] = useState<Transaction[]>([])
  const [reviewCount, setReviewCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [accountId, setAccountId] = useState<number | ''>('')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [direction, setDirection] = useState<'' | 'debit' | 'credit'>('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [loading, setLoading] = useState(true)
  const [debouncedQ, setDebouncedQ] = useState('')

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQ(q), 250)
    return () => window.clearTimeout(timeout)
  }, [q])

  useEffect(() => {
    ;(async () => {
      const [a, c, unc] = await Promise.all([
        api.get<Account[]>('/accounts'),
        api.get<Category[]>('/categories'),
        api.get<Summary>('/analytics/summary'),
      ])
      setAccounts(a)
      setCategories(c)
      setReviewCount(unc.uncategorized_count)
      if (typeof window !== 'undefined') {
        const params = new URLSearchParams(window.location.search)
        if (params.get('review') === 'uncategorized') setCategoryId(0)
      }
    })().catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    ;(async () => {
      const r = await api.get<Transaction[]>('/transactions', {
        q: debouncedQ, account_id: accountId || undefined, category_id: categoryId === '' ? undefined : categoryId,
        direction: direction || undefined, start: start || undefined, end: end || undefined, limit: 1000,
      })
      if (alive) { setItems(r); setLoading(false) }
    })().catch((e: Error) => { if (alive) { setError(e.message); setLoading(false) } })
    return () => { alive = false }
  }, [debouncedQ, accountId, categoryId, direction, start, end])

  async function updateCategory(id: number, cat: number | null) {
    setSavingId(id)
    setError(null)
    try {
      await api.patch(`/transactions/${id}`, { category_id: cat })
      const before = items.find((x) => x.id === id)
      const neededReview = before && (!before.category_id || before.category_source === 'label_review')
      if (neededReview && cat) setReviewCount((count) => Math.max(0, count - 1))
      if (before && !neededReview && !cat) setReviewCount((count) => count + 1)
      setItems((xs) => xs.map((x) => x.id === id ? { ...x, category_id: cat ?? undefined, category_name: categories.find(c => c.id === cat)?.name, category_color: categories.find(c => c.id === cat)?.color, category_source: 'user' } : x).filter((x) => categoryId === '' || (categoryId === 0 ? !x.category_id || x.category_source === 'label_review' : x.category_id === categoryId)))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update this category.') }
    finally { setSavingId(null) }
  }

  const total = useMemo(() => items.reduce((a, t) => a + (t.direction === 'debit' ? Math.abs(t.amount) : 0), 0), [items])
  const income = useMemo(() => items.reduce((a, t) => a + (t.direction === 'credit' ? t.amount : 0), 0), [items])
  const bankNoteCount = useMemo(() => items.filter((t) => t.note).length, [items])
  const hasFilters = Boolean(q || accountId || categoryId !== '' || direction || start || end)

  function exportUrl() {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    if (accountId) params.set('account_id', String(accountId))
    if (q) params.set('q', q)
    if (categoryId !== '') params.set('category_id', String(categoryId))
    if (direction) params.set('direction', direction)
    return `/api/export/csv?${params.toString()}`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-2 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Transactions</h1>
          <p className="text-muted text-sm">{loading ? 'Loading…' : `${items.length} visible rows · ${inr(total)} debits · ${inr(income)} credits`}</p>
        </div>
        <a className="btn" href={exportUrl()}><Download size={14} /> Export CSV</a>
      </div>

      {error ? <div role="alert" className="notice text-red-400">Couldn’t complete the request: {error}</div> : null}
      <div className="card grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3 items-end">
        <div className="col-span-2 flex flex-col gap-1">
          <label className="text-xs text-muted">Search</label>
          <div className="relative">
            <Search size={14} className="absolute left-2 top-2.5 text-muted" />
            <input aria-label="Search transactions" type="search" className="input pl-8 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Merchant or description" />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">Account</label>
          <select aria-label="Account" className="input" value={accountId} onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">All</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">Category</label>
          <select aria-label="Category" className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">All</option>
            <option value={0}>Needs review</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">Direction</label>
          <select aria-label="Direction" className="input" value={direction} onChange={(e) => setDirection(e.target.value as any)}>
            <option value="">All</option>
            <option value="debit">Debits (money out)</option>
            <option value="credit">Credits (money in)</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">From</label>
          <input aria-label="From date" type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted">To</label>
          <input aria-label="To date" type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <button className="rounded-lg border border-border bg-surface p-3 text-left hover:border-slate-600 transition" onClick={() => setCategoryId(0)}>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Needs review</span>
            {reviewCount ? <AlertTriangle size={14} className="text-amber-300" /> : <CheckCircle2 size={14} className="text-emerald-300" />}
          </div>
          <div className="text-2xl font-semibold mt-1">{reviewCount}</div>
          <div className="text-xs text-muted mt-1">Uncategorized rows and unclear bank notes</div>
        </button>
        <button className="rounded-lg border border-border bg-surface p-3 text-left hover:border-slate-600 transition" onClick={() => { setQ(''); setCategoryId(''); setDirection('debit') }}>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Debit rows</span>
            <Filter size={14} className="text-muted" />
          </div>
          <div className="text-2xl font-semibold mt-1">{items.filter((t) => t.direction === 'debit').length}</div>
          <div className="text-xs text-muted mt-1">Current result set</div>
        </button>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Bank notes found</span>
            <Tags size={14} className="text-muted" />
          </div>
          <div className="text-2xl font-semibold mt-1">{bankNoteCount}</div>
          <div className="text-xs text-muted mt-1">Visible rows with bank notes</div>
        </div>
      </div>

      <div className="flex justify-between items-center gap-3 flex-wrap text-xs text-muted">
        <p>Debits and credits include transfers and card repayments.</p>
        {hasFilters ? <button className="btn btn-ghost text-xs" onClick={() => { setQ(''); setAccountId(''); setCategoryId(''); setDirection(''); setStart(''); setEnd('') }}>Clear filters</button> : null}
      </div>
      {items.length === 1000 ? <p className="notice">Showing the first 1,000 matching rows. Narrow the dates or export CSV for all matching transactions.</p> : null}
      <div className="card p-0 overflow-hidden" aria-busy={loading}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted text-xs uppercase bg-surface2/30 sticky top-0">
              <tr>
                <th className="text-left table-cell">Date</th>
                <th className="text-left table-cell">Description</th>
                <th className="text-left table-cell">Merchant</th>
                <th className="text-left table-cell">Account</th>
                <th className="text-left table-cell">Category</th>
                <th className="text-right table-cell">Amount</th>
              </tr>
            </thead>
            <tbody>
              {loading ? <tr><td colSpan={6} className="table-cell"><div className="skeleton h-24" aria-label="Loading transactions" /></td></tr> : items.map((t) => (
                <tr key={t.id} className="border-t border-border hover:bg-surface2/20">
                  <td className="table-cell text-muted whitespace-nowrap">{fmtDate(t.posted_at)}</td>
                  <td className="table-cell max-w-[360px]" title={t.description}>
                    {t.note ? (
                      <div className="flex flex-col">
                        <span className="text-cyan-300 font-medium" title="Bank statement note">“{t.note}”</span>
                        <span className="text-xs text-muted truncate">{t.description}</span>
                      </div>
                    ) : (
                      <span className="truncate block">{t.description}</span>
                    )}
                  </td>
                  <td className="table-cell">{t.merchant || <span className="text-muted">—</span>}</td>
                  <td className="table-cell text-muted">{t.account_name}</td>
                  <td className="table-cell">
                    <select
                      className="input py-1 text-xs"
                      aria-label={`Category for ${t.merchant || t.description}`}
                      disabled={savingId !== null}
                      value={t.category_id ?? ''}
                      onChange={(e) => updateCategory(t.id, e.target.value ? Number(e.target.value) : null)}
                    >
                      <option value="">— Uncategorized —</option>
                      {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                    {t.category_source ? (
                      <span className="ml-1 text-[10px] text-muted">{sourceLabel(t.category_source)}</span>
                    ) : null}
                  </td>
                  <td className={`table-cell text-right font-mono whitespace-nowrap ${t.direction === 'debit' ? 'text-red-400' : 'text-emerald-400'}`}>
                    {t.direction === 'credit' ? '+' : '−'}{inr(Math.abs(t.amount))}
                  </td>
                </tr>
              ))}
              {items.length === 0 && !loading ? (
                <tr>
                  <td colSpan={6} className="table-cell text-center text-muted py-8">
                    {hasFilters ? 'No transactions match these filters.' : 'No transactions imported yet.'}
                    {!hasFilters ? <a href="/upload" className="ml-2 text-cyan-300 hover:underline">Open upload</a> : null}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
