'use client'

import { useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { api, Account, Statement } from '@/lib/api'
import { UploadCloud, FileText, AlertTriangle, CheckCircle2, Plus, Zap, Lock, Receipt, GaugeCircle } from 'lucide-react'

export default function UploadPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [statements, setStatements] = useState<Statement[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<any | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [savingAccount, setSavingAccount] = useState(false)

  // new account modal
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newKind, setNewKind] = useState('bank')
  const [newInst, setNewInst] = useState('')

  async function refresh() {
    const [a, s] = await Promise.all([api.get<Account[]>('/accounts'), api.get<Statement[]>('/upload/statements')])
    setAccounts(a)
    setStatements(s)
  }

  useEffect(() => { refresh().catch((e: Error) => setError(e.message)).finally(() => setLoading(false)) }, [])
  useEffect(() => { if (!selected && accounts.length) setSelected(accounts[0].id) }, [accounts, selected])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: false,
    disabled: busy || !selected,
    onDropRejected: () => setError('Choose one PDF, Excel, or CSV statement at a time.'),
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
    onDrop: async (files) => {
      if (!selected) { setError('Pick an account first'); return }
      if (!files.length) return
      setBusy(true); setError(null); setResult(null)
      try {
        const fd = new FormData()
        fd.append('file', files[0])
        fd.append('account_id', String(selected))
        if (password) fd.append('password', password)
        const r = await api.upload('/upload', fd)
        setResult(r)
        setPassword('')
        await refresh()
      } catch (e: any) {
        setError(e.message)
      } finally { setBusy(false) }
    },
  })

  async function createAccount() {
    if (!newName.trim()) return
    setSavingAccount(true)
    setError(null)
    try {
      const a = await api.post<Account>('/accounts', { name: newName.trim(), kind: newKind, institution: newInst || null })
      setNewName(''); setNewInst(''); setShowNew(false)
      await refresh()
      setSelected(a.id)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not create the account.') }
    finally { setSavingAccount(false) }
  }

  async function quickSetup() {
    setSavingAccount(true)
    try {
    const r = await api.post<{ created: string[]; skipped: string[] }>('/admin/quick-setup', null)
    await refresh()
    setError(null)
    setResult({ inserted: 0, duplicates: 0, warnings: [], _quickSetupMsg: `Created ${r.created.length} accounts${r.skipped.length ? ` (${r.skipped.length} already existed)` : ''}.` })
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not create accounts.') }
    finally { setSavingAccount(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="page-eyebrow mb-2">Build your picture</div>
        <h1 className="text-2xl font-semibold">Your statements, together.</h1>
        <p className="text-muted text-sm">Import bank and credit-card statements, then review exactly what changed.</p>
      </div>

      <div className="card space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-sm text-muted">Account</label>
          <select aria-label="Statement account" disabled={busy || loading} className="input w-full sm:w-auto sm:min-w-[220px]" value={selected ?? ''} onChange={(e) => setSelected(Number(e.target.value))}>
            {accounts.length === 0 ? <option value="">No accounts yet</option> : null}
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.name} {a.last4 ? `••${a.last4}` : ''} ({a.kind})</option>
            ))}
          </select>
          <button className="btn" disabled={busy} aria-expanded={showNew} onClick={() => setShowNew((v) => !v)}><Plus size={14} /> New account</button>
          {accounts.length === 0 ? (
            <button className="btn btn-primary" disabled={savingAccount || loading} onClick={quickSetup} title="Create common savings and credit-card accounts for ICICI, HDFC, SBI, Canara, and Axis">
              <Zap size={14} /> Create common accounts
            </button>
          ) : null}
        </div>

        {showNew ? (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Name</label>
              <input aria-label="Account name" autoFocus className="input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="HDFC Savings" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Kind</label>
              <select aria-label="Account kind" className="input" value={newKind} onChange={(e) => setNewKind(e.target.value)}>
                <option value="bank">Bank</option>
                <option value="credit_card">Credit Card</option>
                <option value="wallet">Wallet</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted">Institution</label>
              <input aria-label="Institution" className="input" value={newInst} onChange={(e) => setNewInst(e.target.value)} placeholder="HDFC, ICICI, Amex..." />
            </div>
            <button className="btn btn-primary" disabled={savingAccount || !newName.trim()} onClick={createAccount}>{savingAccount ? 'Creating…' : 'Create account'}</button>
          </div>
        ) : null}

        <div className="flex items-center gap-2 flex-wrap">
          <Lock size={14} className="text-muted" />
          <label className="text-xs text-muted">PDF password (only if encrypted)</label>
          <input
            type="password"
            aria-label="PDF password"
            disabled={busy}
            className="input flex-1 max-w-xs"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="leave blank if not encrypted"
            autoComplete="off"
          />
        </div>

        <div
          {...getRootProps({ role: 'button', 'aria-label': 'Choose a statement to import' })}
          aria-disabled={busy || !selected}
          aria-busy={busy}
          data-active={isDragActive}
          className="upload-zone"
        >
          <input {...getInputProps()} />
          <UploadCloud size={32} strokeWidth={1.5} className="mx-auto text-accent mb-4" />
          <div className="text-base font-medium" role="status">
            {busy ? 'Reading your statement…' : isDragActive ? 'Drop to upload' : 'Drop your statement here'}
          </div>
          <div className="text-xs text-accent mt-4">{selected ? 'or click to browse files' : 'Create an account above to get started'}</div>
          <div className="text-xs text-muted mt-1">
            {selected
              ? `Selected account: ${accounts.find((a) => a.id === selected)?.name || 'account'}`
              : 'Create or select an account first'} · PDF, XLSX, XLS, CSV
          </div>
        </div>

        {error ? (
          <div role="alert" className="notice flex items-center gap-2 text-red-400 text-sm"><AlertTriangle size={16} /> {error}</div>
        ) : null}

        {result ? <UploadResultPanel result={result} /> : null}
      </div>

      <div className="card">
        <h3 className="font-medium mb-3 flex items-center gap-2"><FileText size={16} /> Uploaded statements</h3>
        {loading ? <div className="skeleton h-20" aria-label="Loading statements" /> : statements.length === 0 ? (
          <p className="text-sm text-muted py-5">Your imported statements will appear here, with a summary of new and duplicate transactions.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted text-xs uppercase">
                <tr>
                  <th className="text-left table-cell">File</th>
                  <th className="text-left table-cell">Period</th>
                  <th className="text-right table-cell">Parsed</th>
                  <th className="text-right table-cell">Inserted</th>
                  <th className="text-right table-cell">Dups</th>
                  <th className="text-right table-cell text-red-400">Debits</th>
                  <th className="text-right table-cell text-emerald-400">Credits</th>
                  <th className="table-cell"></th>
                </tr>
              </thead>
              <tbody>
                {statements.map((s) => (
                  <StatementRow key={s.id} s={s} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function UploadResultPanel({ result }: { result: any }) {
  if (result._quickSetupMsg) {
    return (
      <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
        <div className="flex items-center gap-2 text-emerald-300"><CheckCircle2 size={16} /> {result._quickSetupMsg}</div>
      </div>
    )
  }

  const parsed = result.statement?.n_parsed ?? 0
  const inserted = result.inserted ?? 0
  const duplicates = result.duplicates ?? 0
  const warnings = result.warnings ?? []
  const tone = inserted > 0 ? 'emerald' : parsed > 0 && duplicates > 0 ? 'cyan' : 'amber'
  const title = inserted > 0 ? 'Import completed' : parsed > 0 && duplicates > 0 ? 'Already imported' : 'No new transactions imported'
  const detail = inserted > 0
    ? `${inserted} new transactions are ready for review.`
    : parsed > 0 && duplicates > 0
      ? `${duplicates} duplicates were skipped from this statement.`
      : 'Open the statement review below to check parser details and sample rows.'

  return (
    <div className={`rounded-lg border p-3 text-sm ${tone === 'emerald' ? 'border-emerald-500/40 bg-emerald-500/5' : tone === 'cyan' ? 'border-cyan-500/40 bg-cyan-500/5' : 'border-amber-500/40 bg-amber-500/5'}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className={`flex items-center gap-2 font-medium ${tone === 'amber' ? 'text-amber-300' : tone === 'cyan' ? 'text-cyan-300' : 'text-emerald-300'}`}>
            {tone === 'amber' ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
            {title}
          </div>
          <div className="text-xs text-muted mt-1">{detail}</div>
        </div>
        <div className="flex gap-2">
          <a href="/transactions?review=uncategorized" className="btn btn-ghost text-xs"><Receipt size={14} /> Review rows</a>
          <a href="/" className="btn btn-ghost text-xs"><GaugeCircle size={14} /> Dashboard</a>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3">
        <div className="rounded-lg bg-surface2/50 p-2">
          <div className="text-[10px] text-muted uppercase tracking-wider">Parsed</div>
          <div className="text-lg font-semibold">{parsed}</div>
        </div>
        <div className="rounded-lg bg-surface2/50 p-2">
          <div className="text-[10px] text-muted uppercase tracking-wider">Inserted</div>
          <div className="text-lg font-semibold text-emerald-300">{inserted}</div>
        </div>
        <div className="rounded-lg bg-surface2/50 p-2">
          <div className="text-[10px] text-muted uppercase tracking-wider">Duplicates</div>
          <div className="text-lg font-semibold text-muted">{duplicates}</div>
        </div>
      </div>
      {warnings.length ? (
        <details className="text-amber-300 mt-3">
          <summary className="cursor-pointer">Parser notes ({warnings.length})</summary>
          <pre className="text-xs whitespace-pre-wrap mt-2 text-amber-200/90">{warnings.join('\n')}</pre>
        </details>
      ) : null}
    </div>
  )
}

function StatementRow({ s }: { s: Statement }) {
  const [open, setOpen] = useState(false)
  const [sample, setSample] = useState<any[] | null>(null)
  const credits = s.credit_count ?? 0
  const debits = s.debit_count ?? 0
  const noCredits = (s.n_inserted ?? 0) > 0 && credits === 0
  const status = s.n_parsed === 0
    ? { label: 'Not parsed', cls: 'text-amber-300 border-amber-500/60' }
    : s.n_inserted === 0 && s.n_duplicates > 0
      ? { label: 'Duplicate', cls: 'text-cyan-300 border-cyan-500/60' }
      : noCredits
        ? { label: 'Review', cls: 'text-amber-300 border-amber-500/60' }
        : { label: 'Imported', cls: 'text-emerald-300 border-emerald-500/60' }

  async function toggle() {
    if (!open && sample === null) {
      try {
        const rows = await api.get<any[]>(`/upload/statements/${s.id}/transactions`, { limit: 10 })
        setSample(rows)
      } catch { setSample([]) }
    }
    setOpen((v) => !v)
  }

  return (
    <>
      <tr className="border-t border-border">
        <td className="table-cell">{s.filename} <span className="text-xs text-muted">({s.detected_format})</span></td>
        <td className="table-cell text-muted">{s.period_start || 'Not detected'} to {s.period_end || 'Not detected'}</td>
        <td className="table-cell text-right">{s.n_parsed}</td>
        <td className="table-cell text-right text-emerald-400">{s.n_inserted}</td>
        <td className="table-cell text-right text-muted">{s.n_duplicates}</td>
        <td className="table-cell text-right text-red-400">{debits}</td>
        <td className={`table-cell text-right ${noCredits ? 'text-amber-400 font-semibold' : 'text-emerald-400'}`}>
          {credits}
        </td>
        <td className="table-cell text-right">
          <span className={`chip mr-2 ${status.cls}`}>{status.label}</span>
          <button className="btn btn-ghost text-xs" onClick={toggle}>
            {open ? 'Hide' : 'Review'}
          </button>
        </td>
      </tr>
      {open ? (
        <tr className="border-t border-border bg-surface2/20">
          <td colSpan={8} className="table-cell">
            {noCredits ? (
              <div className="text-amber-400 text-xs mb-2">
                This statement parsed {debits} debits and 0 credits. If the source file has credit entries,
                check the parser details below to see which columns were detected.
              </div>
            ) : null}
            {s.parse_log ? (
              <details className="mb-2">
                <summary className="text-xs text-muted cursor-pointer">Parser details</summary>
                <pre className="text-xs whitespace-pre-wrap text-muted mt-1">{s.parse_log}</pre>
              </details>
            ) : <div className="text-xs text-muted">No parse log.</div>}
            {sample && sample.length > 0 ? (
              <div className="mt-2">
                <div className="text-xs text-muted mb-1">First {sample.length} parsed rows:</div>
                <table className="w-full text-xs">
                  <thead className="text-muted">
                    <tr>
                      <th className="text-left py-1">Date</th>
                      <th className="text-left py-1">Description</th>
                      <th className="text-left py-1">Merchant</th>
                      <th className="text-right py-1">Amount</th>
                      <th className="text-left py-1">Dir</th>
                      <th className="text-left py-1">Category</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sample.map((r) => (
                      <tr key={r.id} className="border-t border-border/30">
                        <td className="py-1 pr-2 text-muted">{r.posted_at}</td>
                        <td className="py-1 pr-2 max-w-[280px] truncate" title={r.description}>{r.description}</td>
                        <td className="py-1 pr-2">{r.merchant || '—'}</td>
                        <td className={`py-1 pr-2 text-right font-mono ${r.direction === 'debit' ? 'text-red-400' : 'text-emerald-400'}`}>
                          {r.amount}
                        </td>
                        <td className="py-1 pr-2">{r.direction}</td>
                        <td className="py-1 pr-2">{r.category_name || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : sample ? (
              <div className="text-xs text-muted">No rows inserted.</div>
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  )
}
