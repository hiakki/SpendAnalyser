'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, ByCategory, Transaction } from '@/lib/api'
import { fmtDate, inr, inr2, monthLabel } from '@/lib/format'
import { CalendarDays, ChevronDown, ChevronRight } from 'lucide-react'

type WindowMode = 'all' | 'monthly' | 'annual' | 'financial-year' | 'custom'
type DateRange = { start?: string; end?: string }
type CategoryMonth = { month: string; total: number; count: number; categories: ByCategory[] }

function currentMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function currentYear(): string {
  return String(new Date().getFullYear())
}

function currentFinancialYearStart(): string {
  const d = new Date()
  return String(d.getMonth() + 1 >= 4 ? d.getFullYear() : d.getFullYear() - 1)
}

function lastDayOfMonth(month: string): string {
  const [year, rawMonth] = month.split('-').map((v) => Number(v))
  const date = new Date(year, rawMonth, 0)
  return `${year}-${String(rawMonth).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function monthRange(month: string): DateRange {
  return { start: `${month}-01`, end: lastDayOfMonth(month) }
}

function financialYearRange(startYear: string): DateRange {
  const y = Number(startYear)
  if (!Number.isFinite(y)) return {}
  return { start: `${y}-04-01`, end: `${y + 1}-03-31` }
}

function rangeFor(mode: WindowMode, month: string, year: string, fyStartYear: string, start: string, end: string): DateRange {
  if (mode === 'monthly' && month) return monthRange(month)
  if (mode === 'annual' && year) return { start: `${year}-01-01`, end: `${year}-12-31` }
  if (mode === 'financial-year') return financialYearRange(fyStartYear)
  if (mode === 'custom') return { start: start || undefined, end: end || undefined }
  return {}
}

function fyLabel(startYear: string): string {
  const y = Number(startYear)
  if (!Number.isFinite(y)) return 'Financial year'
  return `FY ${y}-${String((y + 1) % 100).padStart(2, '0')}`
}

function windowLabel(mode: WindowMode, month: string, year: string, fyStartYear: string, start: string, end: string) {
  if (mode === 'monthly') return month ? monthLabel(month) : 'All months'
  if (mode === 'annual') return year
  if (mode === 'financial-year') return fyLabel(fyStartYear)
  if (mode === 'custom') return [start || 'Start', end || 'End'].join(' to ')
  return 'All imported transactions'
}

function ModeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={`px-3 py-2 text-sm transition ${active ? 'bg-cyan-500 text-slate-950' : 'bg-surface hover:bg-surface2 text-slate-200'}`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function monthToFinancialYearStart(month: string): string {
  const [year, rawMonth] = month.split('-').map((v) => Number(v))
  return String(rawMonth >= 4 ? year : year - 1)
}

export default function CategorySpendBreakdown() {
  const [mode, setMode] = useState<WindowMode>('all')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState(currentYear())
  const [fyStartYear, setFyStartYear] = useState(currentFinancialYearStart())
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [categories, setCategories] = useState<ByCategory[]>([])
  const [monthGroups, setMonthGroups] = useState<CategoryMonth[]>([])
  const [allMonthOptions, setAllMonthOptions] = useState<string[]>([])
  const [expandedMonth, setExpandedMonth] = useState<string | null>(null)
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)
  const [txnsByCategory, setTxnsByCategory] = useState<Record<string, Transaction[]>>({})
  const [loadingCategories, setLoadingCategories] = useState(true)
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const range = useMemo(() => rangeFor(mode, month, year, fyStartYear, start, end), [mode, month, year, fyStartYear, start, end])
  const showMonthGroups = (mode === 'monthly' && !month) || mode === 'financial-year'
  const cacheSuffix = `${range.start || ''}:${range.end || ''}`
  const totalSpend = categories.reduce((sum, c) => sum + c.total, 0)
  const totalTransactions = categories.reduce((sum, c) => sum + c.count, 0)

  const financialYearOptions = useMemo(() => {
    const years = new Set<string>([currentFinancialYearStart(), fyStartYear])
    allMonthOptions.forEach((m) => years.add(monthToFinancialYearStart(m)))
    return Array.from(years).sort((a, b) => Number(b) - Number(a))
  }, [allMonthOptions, fyStartYear])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const rows = await api.get<CategoryMonth[]>('/analytics/by-category-month')
        if (!alive) return
        setAllMonthOptions(rows.map((r) => r.month).sort((a, b) => b.localeCompare(a)))
      } catch {
        if (alive) setAllMonthOptions([currentMonth()])
      }
    })()
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    setLoadingCategories(true)
    setError(null)
    setExpandedCategory(null)
    setTxnsByCategory({})

    ;(async () => {
      try {
        const [categoryRows, groupedRows] = await Promise.all([
          api.get<ByCategory[]>('/analytics/by-category', range),
          showMonthGroups ? api.get<CategoryMonth[]>('/analytics/by-category-month', range) : Promise.resolve([]),
        ])
        if (!alive) return
        setCategories(categoryRows)
        setMonthGroups(sortMonthGroups(groupedRows, mode))
        setExpandedMonth((prev) => {
          if (!showMonthGroups || groupedRows.length === 0) return null
          if (prev && groupedRows.some((g) => g.month === prev)) return prev
          return sortMonthGroups(groupedRows, mode)[0]?.month || null
        })
      } catch (e: any) {
        if (alive) setError(e.message)
      } finally {
        if (alive) setLoadingCategories(false)
      }
    })()

    return () => { alive = false }
  }, [range, showMonthGroups, mode])

  async function toggleCategory(categoryId: number, scopedRange: DateRange, scopeKey: string) {
    const categoryKey = `${scopeKey}:${categoryId}:${scopedRange.start || ''}:${scopedRange.end || ''}`
    if (expandedCategory === categoryKey) {
      setExpandedCategory(null)
      return
    }

    setExpandedCategory(categoryKey)
    setError(null)
    if (txnsByCategory[categoryKey]) return

    setLoadingCategory(categoryKey)
    try {
      const rows = await api.get<Transaction[]>('/transactions', {
        ...scopedRange,
        category_id: categoryId,
        direction: 'debit',
        limit: 5000,
      })
      setTxnsByCategory((prev) => ({ ...prev, [categoryKey]: rows }))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoadingCategory(null)
    }
  }

  function renderCategoryRows(rows: ByCategory[], scopedRange: DateRange, scopeKey: string) {
    return rows.map((c) => {
      const categoryKey = `${scopeKey}:${c.category_id}:${scopedRange.start || ''}:${scopedRange.end || ''}`
      const isOpen = expandedCategory === categoryKey
      const txns = txnsByCategory[categoryKey] || []
      const color = c.color || '#64748b'

      return (
        <div key={categoryKey}>
          <button
            className="w-full grid grid-cols-[auto_1fr_auto] items-center gap-3 py-3 text-left hover:bg-surface2/20 px-2 -mx-2 rounded-lg transition"
            onClick={() => toggleCategory(c.category_id, scopedRange, scopeKey)}
            aria-expanded={isOpen}
            type="button"
          >
            {isOpen ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                <span className="font-medium truncate">{c.category_name}</span>
              </span>
              <span className="text-xs text-muted">{c.count} transactions</span>
            </span>
            <span className="text-right">
              <span className="block font-mono text-red-300">{inr(c.total)}</span>
              <span className="text-[10px] text-muted uppercase tracking-wider">spent</span>
            </span>
          </button>

          {isOpen ? (
            <div className="pb-4 pl-8">
              {loadingCategory === categoryKey ? (
                <div className="text-xs text-muted py-3">Loading transactions...</div>
              ) : txns.length ? (
                <TransactionTable rows={txns} />
              ) : (
                <div className="text-xs text-muted py-3">No spend transactions found for this category.</div>
              )}
            </div>
          ) : null}
        </div>
      )
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Where your money goes.</h1>
          <p className="text-sm text-muted">Debit outflow grouped by category. Includes transfers and card repayments; expand a category to review its transactions.</p>
        </div>
        <span className="chip"><CalendarDays size={14} /> {windowLabel(mode, month, year, fyStartYear, start, end)}</span>
      </div>

      <div className="card space-y-4">
        <div className="flex flex-wrap gap-3 items-end justify-between">
          <div className="flex flex-wrap overflow-hidden rounded-lg border border-border">
            <ModeButton active={mode === 'all'} label="All time" onClick={() => setMode('all')} />
            <ModeButton active={mode === 'monthly'} label="Monthly" onClick={() => setMode('monthly')} />
            <ModeButton active={mode === 'annual'} label="Annual" onClick={() => setMode('annual')} />
            <ModeButton active={mode === 'financial-year'} label="Financial year" onClick={() => setMode('financial-year')} />
            <ModeButton active={mode === 'custom'} label="Custom" onClick={() => setMode('custom')} />
          </div>

          {mode === 'monthly' ? (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Month</label>
              <select className="input min-w-[180px]" value={month} onChange={(e) => setMonth(e.target.value)}>
                <option value="">All months</option>
                {allMonthOptions.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
              </select>
            </div>
          ) : null}

          {mode === 'annual' ? (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Calendar year</label>
              <input type="number" className="input w-32" min="2000" max="2100" value={year} onChange={(e) => setYear(e.target.value)} />
            </div>
          ) : null}

          {mode === 'financial-year' ? (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Financial year</label>
              <select className="input min-w-[150px]" value={fyStartYear} onChange={(e) => setFyStartYear(e.target.value)}>
                {financialYearOptions.map((fy) => <option key={fy} value={fy}>{fyLabel(fy)}</option>)}
              </select>
            </div>
          ) : null}

          {mode === 'custom' ? (
            <div className="flex flex-wrap gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted">From</label>
                <input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted">To</label>
                <input type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
              </div>
            </div>
          ) : null}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-lg border border-border bg-surface2/30 p-3">
            <div className="text-xs text-muted uppercase tracking-wider">Total outflow</div>
            <div className="text-2xl font-semibold text-red-300 mt-1">{inr(totalSpend)}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface2/30 p-3">
            <div className="text-xs text-muted uppercase tracking-wider">Categories</div>
            <div className="text-2xl font-semibold mt-1">{categories.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface2/30 p-3">
            <div className="text-xs text-muted uppercase tracking-wider">Transactions</div>
            <div className="text-2xl font-semibold mt-1">{totalTransactions}</div>
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="font-medium">{showMonthGroups ? 'Monthly sections' : 'Categories'}</h3>
            <p className="text-xs text-muted mt-1">
              {showMonthGroups ? 'Open a month, then expand a category to see its transactions.' : 'Click any category to expand its spend transactions.'}
            </p>
          </div>
          {loadingCategories ? <span className="text-xs text-muted">Loading...</span> : <span className="text-xs text-muted">{categories.length} categories</span>}
        </div>

        {error ? <div className="text-sm text-red-400 mb-3">Failed to load breakdown: {error}</div> : null}

        {!loadingCategories && categories.length === 0 ? (
          <div className="text-sm text-muted py-8 text-center">No spend transactions found for this time window.</div>
        ) : showMonthGroups ? (
          <div className="divide-y divide-border">
            {monthGroups.map((group) => {
              const isOpen = expandedMonth === group.month
              const scopedRange = monthRange(group.month)
              return (
                <div key={group.month}>
                  <button
                    className="w-full grid grid-cols-[auto_1fr_auto] items-center gap-3 py-3 text-left hover:bg-surface2/20 px-2 -mx-2 rounded-lg transition"
                    onClick={() => setExpandedMonth(isOpen ? null : group.month)}
                    aria-expanded={isOpen}
                    type="button"
                  >
                    {isOpen ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
                    <span>
                      <span className="font-medium">{monthLabel(group.month)}</span>
                      <span className="block text-xs text-muted">{group.count} transactions across {group.categories.length} categories</span>
                    </span>
                    <span className="text-right">
                      <span className="block font-mono text-red-300">{inr(group.total)}</span>
                      <span className="text-[10px] text-muted uppercase tracking-wider">spent</span>
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="pb-4 pl-8 divide-y divide-border/70">
                      {renderCategoryRows(group.categories, scopedRange, group.month)}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {renderCategoryRows(categories, range, `range:${cacheSuffix}`)}
          </div>
        )}
      </div>
    </div>
  )
}

function sortMonthGroups(groups: CategoryMonth[], mode: WindowMode) {
  return [...groups].sort((a, b) => mode === 'financial-year' ? a.month.localeCompare(b.month) : b.month.localeCompare(a.month))
}

function TransactionTable({ rows }: { rows: Transaction[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead className="bg-surface2/40 text-muted uppercase">
          <tr>
            <th className="text-left px-3 py-2">Date</th>
            <th className="text-left px-3 py-2">Merchant</th>
            <th className="text-left px-3 py-2">Raw transaction msg</th>
            <th className="text-left px-3 py-2">Account</th>
            <th className="text-right px-3 py-2">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id} className="border-t border-border/50">
              <td className="px-3 py-2 text-muted whitespace-nowrap">{fmtDate(t.posted_at)}</td>
              <td className="px-3 py-2 min-w-[160px]">{t.merchant || <span className="text-muted">-</span>}</td>
              <td className="px-3 py-2 min-w-[360px] max-w-[620px]" title={t.description}>
                <span className="block truncate">{t.description}</span>
                {t.note ? <span className="block text-[10px] text-cyan-300 truncate">{t.note}</span> : null}
              </td>
              <td className="px-3 py-2 text-muted whitespace-nowrap">{t.account_name}</td>
              <td className="px-3 py-2 text-right font-mono text-red-300 whitespace-nowrap">−{inr2(Math.abs(t.amount))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
