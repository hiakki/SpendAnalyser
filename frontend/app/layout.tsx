import './globals.css'
import type { Metadata } from 'next'
import AppNavigation from '@/components/AppNavigation'

export const metadata: Metadata = {
  title: 'Spend Analyser',
  description: 'Track and analyse personal spending from bank & credit-card statements.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link btn btn-primary">Skip to content</a>
        <div className="app-shell">
          <AppNavigation />
          <main id="main-content" tabIndex={-1} className="app-main">
            <div className="workspace-bar"><span>Personal finance / Your workspace</span><span>INR · ₹</span></div>
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}
