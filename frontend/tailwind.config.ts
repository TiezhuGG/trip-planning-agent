import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        iris: '#6d61e3',
        irisDark: '#5847cf',
        ink: '#1f2a44',
        mist: '#eef1f9',
        panel: '#f7f8fc',
        slate: '#94a3b8',
      },
      boxShadow: {
        glow: '0 28px 80px rgba(88, 71, 207, 0.25)',
        card: '0 14px 40px rgba(32, 40, 74, 0.08)',
      },
      borderRadius: {
        '4xl': '2rem',
      },
      fontFamily: {
        display: ['"HarmonyOS Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        body: ['"HarmonyOS Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
