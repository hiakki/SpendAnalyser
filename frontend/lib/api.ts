const BASE = ''

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: any = null
    try { detail = await res.json() } catch {}
    const msg = detail?.detail || `${res.status} ${res.statusText}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json() as Promise<T>
}

export const api = {
  async get<T>(path: string, params?: Record<string, any>): Promise<T> {
    const qs = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : ''
    return jsonOrThrow<T>(await fetch(`${BASE}/api${path}${qs}`, { cache: 'no-store' }))
  },
  async post<T>(path: string, body?: any): Promise<T> {
    return jsonOrThrow<T>(await fetch(`${BASE}/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }))
  },
  async patch<T>(path: string, body?: any): Promise<T> {
    return jsonOrThrow<T>(await fetch(`${BASE}/api${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }))
  },
  async del<T>(path: string): Promise<T> {
    return jsonOrThrow<T>(await fetch(`${BASE}/api${path}`, { method: 'DELETE' }))
  },
  async upload(path: string, fd: FormData): Promise<any> {
    return jsonOrThrow<any>(await fetch(`${BASE}/api${path}`, { method: 'POST', body: fd }))
  },
}

export type Account = { id: number; name: string; kind: string; institution?: string; last4?: string; currency: string }
export type Category = { id: number; name: string; icon?: string; color?: string }
export type Rule = { id: number; pattern: string; is_regex: boolean; category_id: number; priority: number; note?: string }
export type Transaction = {
  id: number
  account_id: number
  account_name?: string
  posted_at: string
  description: string
  merchant?: string
  amount: number
  currency: string
  direction: 'debit' | 'credit'
  category_id?: number
  category_name?: string
  category_color?: string
  category_source?: string
  note?: string
}
export type Statement = {
  id: number
  account_id: number
  filename: string
  file_kind?: string
  detected_format?: string
  period_start?: string
  period_end?: string
  n_parsed: number
  n_inserted: number
  n_duplicates: number
  debit_count?: number
  credit_count?: number
  parse_log?: string
}
export type Budget = { id: number; category_id: number; category_name?: string; month: string; amount: number }
export type Summary = { spend: number; income: number; net: number; n_transactions: number; uncategorized_count: number }
export type ByCategory = { category_id: number; category_name: string; color?: string; total: number; count: number }
export type ByMonth = { month: string; spend: number; income: number; net: number; count: number }
export type BudgetStatus = { category_id: number; category_name: string; color?: string; budget: number; actual: number; remaining: number; percent: number; over: boolean }
export type Recurring = {
  key: string
  merchant: string
  category_name?: string
  count: number
  avg_amount: number
  avg_cadence_days: number
  amount_volatility_pct: number
  last_seen: string
  next_estimated: string
  active: boolean
}
export type Anomaly = { transaction_id: number; posted_at: string; merchant?: string; description: string; amount: number; category_name?: string; category_mean: number; z_score: number }
