export function inr(amount: number): string {
  const n = Number(amount || 0)
  const sign = n < 0 ? '-' : ''
  const abs = Math.abs(n)
  return sign + '₹' + abs.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function inr2(amount: number): string {
  const n = Number(amount || 0)
  const sign = n < 0 ? '-' : ''
  const abs = Math.abs(n)
  return sign + '₹' + abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

export function monthLabel(ym: string): string {
  const [y, m] = ym.split('-').map((s) => parseInt(s, 10))
  return new Date(y, m - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}
