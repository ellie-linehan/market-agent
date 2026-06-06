import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Market Intelligence',
  description: 'B2B competitive landscape and ICP analysis',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-cream font-sans antialiased">{children}</body>
    </html>
  )
}
