import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Market Intelligence',
  description: 'B2B competitive landscape and ICP analysis',
  icons: {
    icon: [
      { url: '/favicon-light.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: light)' },
      { url: '/favicon-dark.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: dark)' },
    ],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-cream font-sans antialiased">{children}</body>
    </html>
  )
}
