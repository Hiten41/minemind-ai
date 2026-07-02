import type { Metadata } from 'next'

import AuthGate from '@/components/auth/AuthGate'

import './globals.css'

export const metadata: Metadata = {
  title: 'MineMind AI',
  description: 'AI Mining Operations Assistant'
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
