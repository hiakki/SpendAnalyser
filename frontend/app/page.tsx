'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, Account, ByCategory, ByMonth, Statement, Summary, Transaction } from '@/lib/api'
import { inr, inr2, monthLabel, fmtDate } from '@/lib/format'
import { Bar, BarChart, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { TrendingDown, TrendingUp, Activity, Banknote, Upload, Receipt, Settings, CheckCircle2, AlertTriangle } from 'lucide-react'

function Kpi({ label, value, hint, icon: Icon, tone = 'default' }: any) {
  const toneCls = tone === 'red' ? 'text-red-400' : tone === 'green' ? 'text-emerald-400' : 'text-slate-100'
  return (
    <div className="kpi">
      <div className="flex items-center justify-between">
        <span className="kpi-label">{label}</span>
        {Icon ? <Icon size={16} className="text-muted" /> : null}
      </div>
      <span className={`kpi-value ${toneCls}`}>{value}</span>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </div>
  )
}

function SetupStep({ icon: Icon, title, detail, href, action }: any) {
  return (
    <a href={href} className="card flex items-start gap-3 hover:border-slate-600 transition">
      <span className="mt-0.5 rounded-lg bg-surface2 p-2 text-cyan-300">
        <Icon size={18} />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted mt-1">{detail}</span>
        <span className="block text-xs text-cyan-300 mt-3">{action}</span>
      </span>
    </a>
  )
}

function ImportHealth({ accounts, statements, uncategorized }: { accounts: Account[]; statements: Statement[]; uncategorized: number }) {
  const latest = statements[0]
  const hasImportIssue = latest && latest.n_parsed === 0
  const hasReview = uncategorized > 0 || hasImportIssue

  return (
    <div className="card">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-medium">Import health</h2>
          <p className="text-xs text-muted mt-1">
            {hasReview ? 'A few items need review before the dashboard is fully reliable.' : 'Statements are imported and categorized.'}
          </p>
        </div>
        <span className={`chip ${hasReview ? 'text-amber-300' : 'text-emerald-300'}`} style={{ borderColor: hasReview ? '#f59e0b' : '#10b981' }}>
          {hasReview ? 'Needs review' : 'Ready'}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
        <a href="/upload" className="rounded-lg border border-border bg-surface2/30 p-3 hover:border-slate-600 transition">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Accounts</span>
            <Settings size={14} className="text-muted" />
          </div>
          <div className="text-2xl font-semibold mt-1">{accounts.length}</div>
          <div className="text-xs text-muted mt-1">{accounts.length ? 'Ready for imports' : 'Create one before uploading'}</div>
        </a>
        <a href="/upload" className="rounded-lg border border-border bg-surface2/30 p-3 hover:border-slate-600 transition">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Statements</span>
            <Upload size={14} className="text-muted" />
          </div>
          <div className="text-2xl font-semibold mt-1">{statements.length}</div>
          <div className={`text-xs mt-1 ${hasImportIssue ? 'text-amber-300' : 'text-muted'}`}>
            {latest ? `${latest.n_inserted} inserted in latest import` : 'No imports yet'}
          </div>
        </a>
        <a href="/transactions?review=uncategorized" className="rounded-lg border border-border bg-surface2/30 p-3 hover:border-slate-600 transition">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider">Needs Category</span>
            {uncategorized ? <AlertTriangle size={14} className="text-amber-300" /> : <CheckCircle2 size={14} className="text-emerald-300" />}
          </div>
          <div className="text-2xl font-semibold mt-1">{uncategorized}</div>
          <div className="text-xs text-muted mt-1">{uncategorized ? 'Review unmatched rows' : 'No uncategorized rows'}</div>
        </a>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [byCat, setByCat] = useState<ByCategory[]>([])
  const [byMonth, setByMonth] = useState<ByMonth[]>([])
  const [recent, setRecent] = useState<Transaction[]>([])
  const [merchants, setMerchants] = useState<{ merchant: string; total: number; count: number }[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [statements, setStatements] = useState<Statement[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [s, c, m, r, mer, a, st] = await Promise.all([
          api.get<Summary>('/analytics/summary'),
          api.get<ByCategory[]>('/analytics/by-category'),
          api.get<ByMonth[]>('/analytics/by-month'),
          api.get<Transaction[]>('/transactions', { limit: 10 }),
          api.get<{ merchant: string; total: number; count: number }[]>('/analytics/top-merchants', { limit: 10 }),
          api.get<Account[]>('/accounts'),
          api.get<Statement[]>('/upload/statements'),
        ])
        if (!alive) return
        setSummary(s); setByCat(c); setByMonth(m); setRecent(r); setMerchants(mer)
        setAccounts(a); setStatements(st)
      } catch (e: any) {
        setError(e.message)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [])

  if (error) return <div className="card space-y-3" role="alert"><h1 className="text-2xl">Your overview is unavailable</h1><p className="text-muted">We couldn’t load your accounts and transactions. {error}</p><button className="btn" onClick={() => window.location.reload()}>Try again</button></div>
  const empty = !loading && (summary?.n_transactions ?? 0) === 0

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="page-eyebrow mb-2">The bigger picture</div>
          <h1 className="text-2xl font-semibold">Your money, made clear.</h1>
          <p className="text-muted text-sm">A considered view of every account, statement, and transaction.</p>
        </div>
        <Link href="/upload" className="btn btn-primary"><Upload size={15} /> Import statement</Link>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4" aria-busy={loading}>
        <Kpi label="Money out" value={loading ? '—' : inr(summary?.spend ?? 0)} hint="All imported debits" tone="red" icon={TrendingDown} />
        <Kpi label="Money in" value={loading ? '—' : inr(summary?.income ?? 0)} hint="All imported credits" tone="green" icon={TrendingUp} />
        <Kpi label="Net cash flow" value={loading ? '—' : inr(summary?.net ?? 0)} hint="Money in minus money out" tone={summary && summary.net >= 0 ? 'green' : 'red'} icon={Banknote} />
        <Kpi label="Transactions" value={loading ? '—' : (summary?.n_transactions ?? 0).toLocaleString()} hint="Across all imported statements" icon={Activity} />
      </div>
      <p className="text-xs text-muted">Cash-flow totals include transfers and credit-card repayments. These are not adjusted spending or income totals.</p>

      {loading ? <div className="card space-y-5" role="status" aria-label="Loading overview"><div className="skeleton h-5 w-1/3" /><div className="skeleton h-48 w-full" /><p className="text-xs text-muted">Bringing your accounts together…</p></div> : empty ? (
        <div className="space-y-4">
          <div className="onboarding">
            <div>
              <p className="page-eyebrow mb-4">A good place to begin</p>
              <h2 className="onboarding-title">A little clarity starts with one statement.</h2>
              <p className="text-sm text-muted mt-4 mb-6">Bring in a bank or card statement. See where your money goes, review its categories, and build a picture over time.</p>
              <Link href="/upload" className="btn btn-primary">Add your first statement <Upload size={15} /></Link>
            </div>
            <div className="ledger-preview" aria-label="What your statement becomes">
              <div className="ledger-preview-row"><span className="text-muted">01 / Bring it together</span><span>Bank & card accounts</span></div>
              <div className="ledger-preview-row"><span className="text-muted">02 / Find the details</span><span>Clear categories</span></div>
              <div className="ledger-preview-row"><span className="text-muted">03 / See the patterns</span><span>Monthly cash flow</span></div>
              <p className="text-xs text-muted pt-4">PDF, Excel, and CSV statements supported.</p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SetupStep icon={Settings} title="Accounts" detail="Create the bank or card account the file belongs to." href="/upload" action={accounts.length ? `${accounts.length} accounts ready` : 'Create accounts'} />
            <SetupStep icon={Upload} title="Statement import" detail="Upload PDF, XLSX, XLS, or CSV against the right account." href="/upload" action="Import statement" />
            <SetupStep icon={Receipt} title="Review categories" detail="UPI labels and rules are applied automatically, then unmatched rows stay visible." href="/transactions?review=uncategorized" action="Open review list" />
          </div>
        </div>
      ) : (
        <>
          <ImportHealth accounts={accounts} statements={statements} uncategorized={summary?.uncategorized_count ?? 0} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="card lg:col-span-2">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-medium">Monthly trend</h2>
                <span className="text-xs text-muted">Money out & money in</span>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={byMonth}>
                    <XAxis dataKey="month" tickFormatter={monthLabel} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v: any) => inr(v)} />
                    <Tooltip
                      contentStyle={{ background: '#ffffff', border: '1px solid #dfe2d9', borderRadius: 8 }}
                      formatter={(v: any) => inr(Number(v))}
                      labelFormatter={(l: any) => monthLabel(l)}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="spend" name="Money out" stroke="#a86848" strokeWidth={2.5} dot={false} />
                    <Line type="monotone" dataKey="income" name="Money in" stroke="#46754c" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-medium">Outflow by category</h2>
                <a href="/category-spend" className="text-xs text-cyan-400 hover:underline">Open breakdown →</a>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={byCat.slice(0, 8)} dataKey="total" nameKey="category_name" innerRadius={50} outerRadius={90} paddingAngle={2}>
                      {byCat.slice(0, 8).map((c, i) => <Cell key={i} fill={c.color || '#64748b'} />)}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: '#ffffff', border: '1px solid #dfe2d9', borderRadius: 8 }}
                      formatter={(v: any) => inr(Number(v))}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-2 space-y-1 text-sm max-h-32 overflow-y-auto">
                {byCat.slice(0, 8).map((c) => (
                  <li key={c.category_id} className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: c.color || '#64748b' }} />
                      {c.category_name}
                    </span>
                    <span className="text-muted">{inr(c.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card">
              <h2 className="font-medium mb-2">Top merchants by outflow</h2>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={merchants} layout="vertical" margin={{ left: 30 }}>
                    <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v: any) => inr(v)} />
                    <YAxis type="category" dataKey="merchant" width={120} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: '#ffffff', border: '1px solid #dfe2d9', borderRadius: 8 }}
                      formatter={(v: any) => inr(Number(v))}
                    />
                    <Bar dataKey="total" name="Outflow" fill="#73906b" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card overflow-hidden">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-medium">Recent transactions</h2>
                <a href="/transactions" className="text-xs text-cyan-400 hover:underline">View all →</a>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-muted text-xs uppercase">
                    <tr>
                      <th className="text-left table-cell">Date</th>
                      <th className="text-left table-cell">Merchant</th>
                      <th className="text-left table-cell">Category</th>
                      <th className="text-right table-cell">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((t) => (
                      <tr key={t.id} className="border-t border-border">
                        <td className="table-cell text-muted">{fmtDate(t.posted_at)}</td>
                        <td className="table-cell truncate max-w-[180px]" title={t.description}>
                          {t.merchant || t.description}
                        </td>
                        <td className="table-cell">
                          {t.category_name ? (
                            <span className="chip" style={{ borderColor: t.category_color }}>
                              {t.category_name}
                            </span>
                          ) : <span className="text-muted text-xs">—</span>}
                        </td>
                        <td className={`table-cell text-right font-mono ${t.direction === 'debit' ? 'text-red-400' : 'text-emerald-400'}`}>
                          {t.direction === 'credit' ? '+' : '−'}{inr2(Math.abs(t.amount))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
