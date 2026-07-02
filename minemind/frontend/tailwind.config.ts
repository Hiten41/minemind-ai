import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}'
  ],
  theme: {
    extend: {
      colors: {
        bg: '#050508',
        background: '#050508',
        surface: '#0a0a0f',
        card: '#0f0f17',
        'card-hover': '#141420',
        border: '#1a1a2e',
        'border-light': '#222235',
        'card-border': '#1a1a2e',
        gold: '#f59e0b',
        'gold-dim': '#92600a',
        'gold-glow': 'rgba(245,159,11,0.15)',
        success: '#10b981',
        danger: '#ef4444',
        info: '#3b82f6',
        purple: '#8b5cf6',
        'mem-purple': '#8b5cf6',
        muted: '#888888',
        'muted-dark': '#444455'
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace']
      },
      animation: {
        'pulse-slow': 'pulse 3s infinite',
        'fade-in': 'fadeIn 0.3s ease',
        'slide-up': 'slideUp 0.3s ease',
        'slide-in': 'slideIn 0.3s ease'
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' }
        },
        slideIn: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' }
        }
      }
    }
  },
  plugins: []
}

export default config
