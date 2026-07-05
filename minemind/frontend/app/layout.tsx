import type { Metadata } from 'next'

import AuthGate from '@/components/auth/AuthGate'

import './globals.css'

export const metadata: Metadata = {
  title: 'MineMind AI \u2014 Mining Intelligence',
  description:
    'Consolidate regulations, manuals, and incident data into a secure, searchable intelligence network for your mining operation.',
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
