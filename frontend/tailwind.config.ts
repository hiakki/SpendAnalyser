import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#f6f5f0',
        surface: '#ffffff',
        surface2: '#eeeee6',
        border: '#dfe2d9',
        muted: '#657064',
        accent: '#27634c',
      },
      boxShadow: {
        card: '0 1px 2px rgba(39,55,42,0.03)',
      },
    },
  },
  plugins: [],
}
export default config
