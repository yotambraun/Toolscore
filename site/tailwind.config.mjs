/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,ts,jsx,tsx,md,mdx}'],
  theme: {
    extend: {
      colors: {
        // --- Surfaces (dark developer-tool base) ---
        bg: '#070a12', // near-black page background
        surface: '#0d111c', // lifted cards / nav
        elevated: '#141a28', // terminal panels
        line: '#1c2435', // hairline borders
        line2: '#2a3550', // brighter borders / hover

        // --- Brand (from the Toolscore logo) ---
        brand: '#22d3a0', // teal — primary accent
        brand2: '#34e0b4', // lighter teal
        indigo: '#6366f1', // secondary accent (indigo from the tile)
        indigoDeep: '#1e1b4b', // deep indigo brand

        // --- Text ---
        ink: '#e8eef7', // primary text on dark
        muted: '#94a3bd', // secondary text
        faint: '#64748b', // tertiary / captions

        // --- A–F grade palette (the centerpiece accent system) ---
        gradeA: '#22e07a', // bright green
        gradeB: '#5fce62', // green
        gradeC: '#f2b431', // amber
        gradeD: '#f08537', // orange
        gradeF: '#ef4458', // red

        // --- Terminal ANSI-ish helpers ---
        termGreen: '#34e0b4',
        termAmber: '#f2b431',
        termRed: '#ef4458',
        termDim: '#5b6b85',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      backgroundImage: {
        brandgrad: 'linear-gradient(95deg, #22d3a0 0%, #6366f1 100%)',
        gradegrad: 'linear-gradient(90deg, #22e07a 0%, #5fce62 30%, #f2b431 60%, #f08537 80%, #ef4458 100%)',
        'hero-glow':
          'radial-gradient(60% 50% at 50% 25%, rgba(34,211,160,.16), rgba(99,102,241,.10) 45%, transparent 72%)',
      },
      boxShadow: {
        glow: '0 0 50px -12px rgba(34,211,160,.40)',
        'glow-indigo': '0 0 50px -12px rgba(99,102,241,.38)',
        'glow-soft': '0 0 0 1px rgba(34,211,160,.10), 0 18px 40px -20px rgba(0,0,0,.7)',
        panel: '0 1px 0 0 rgba(255,255,255,.03) inset, 0 24px 60px -30px rgba(0,0,0,.85)',
      },
      maxWidth: {
        content: '74rem',
      },
      keyframes: {
        blink: {
          '0%, 49%': { opacity: '1' },
          '50%, 100%': { opacity: '0' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'bar-grow': {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
      },
      animation: {
        blink: 'blink 1.05s step-end infinite',
        'fade-up': 'fade-up .5s ease both',
      },
    },
  },
  plugins: [],
};
