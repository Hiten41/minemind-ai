'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/dashboard', icon: 'H', label: 'Dashboard' },
  { href: '/chat', icon: 'AI', label: 'AI Assistant' },
  { href: '/documents', icon: 'D', label: 'Documents' },
  { href: '/equipment', icon: 'E', label: 'Equipment' },
  { href: '/incidents', icon: '!', label: 'Incidents' },
  { href: '/analytics', icon: 'A', label: 'Analytics' }
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-screen w-[240px] flex-col border-r border-card-border bg-card">
      <div className="border-b border-card-border px-6 py-5">
        <div className="text-xl font-bold text-white">
          MineMind AI
        </div>
      </div>
      <nav className="flex-1 py-5">
        {navItems.map((item) => {
          const active = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 border-l-[3px] px-5 py-3 text-sm transition ${
                active
                  ? 'border-white text-white'
                  : 'border-transparent text-[#888888] hover:border-white/50 hover:text-white'
              }`}
            >
              <span className="flex h-7 w-7 items-center justify-center rounded bg-background text-[11px] font-semibold">
                {item.icon}
              </span>
              {item.label}
            </Link>
          )
        })}
      </nav>
      <div className="border-t border-card-border px-6 py-5 text-sm font-medium text-white/60">
        Private workspace
      </div>
    </aside>
  )
}
