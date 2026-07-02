import type { Metadata } from 'next'

import AuthGate from '@/components/auth/AuthGate'

import './globals.css'

export const metadata: Metadata = {
  title: 'MineMind AI \u2014 Mining Intelligence',
  description:
    'Permanent AI memory for mining operations. Upload regulations, manuals, and incident reports \u2014 MineMind remembers everything forever and answers safety questions with evidence.',
  icons: {
    icon: '/logo.svg'
  }
}

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-white">
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  )
}
