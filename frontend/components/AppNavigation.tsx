'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Wallet, Upload, Receipt, ChartNoAxesCombined, Repeat, Flag, Settings, Tags, ArrowUpRight } from 'lucide-react'

const nav = [
  { href: '/', label: 'Overview', icon: ChartNoAxesCombined },
  { href: '/transactions', label: 'Transactions', icon: Receipt },
  { href: '/category-spend', label: 'Categories', icon: Tags },
  { href: '/budgets', label: 'Budgets', icon: Wallet },
  { href: '/recurring', label: 'Recurring', icon: Repeat },
  { href: '/anomalies', label: 'Unusual spending', icon: Flag },
  { href: '/upload', label: 'Statements', icon: Upload },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export default function AppNavigation() {
  const pathname = usePathname()
  return (
    <aside className="app-sidebar">
      <Link className="brand" href="/" aria-label="Spend home">
        <span className="brand-mark"><ChartNoAxesCombined size={20} aria-hidden="true" /></span>
        <span className="brand-name">spend<span className="text-muted">.</span></span>
      </Link>
      <p className="sidebar-label page-eyebrow px-3 mb-3">Your workspace</p>
      <nav aria-label="Main navigation" className="space-y-1">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className="nav-link" aria-current={pathname === href ? 'page' : undefined}>
            <Icon size={17} strokeWidth={1.7} aria-hidden="true" />{label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer mt-auto pt-8 px-3">
        <div className="border-t border-border pt-5">
          <p className="text-xs font-medium mb-1">Make every entry count.</p>
          <p className="text-xs text-muted mb-4">Bring your statements together. Understand the details.</p>
          <Link href="/upload" className="text-xs font-semibold text-accent inline-flex items-center gap-2">Import a statement <ArrowUpRight size={14} /></Link>
        </div>
      </div>
    </aside>
  )
}
