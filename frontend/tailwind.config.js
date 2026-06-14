/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#CCFBF1',
          100: '#99F6E4',
          500: '#14B8A6',
          600: '#0D9488',
          700: '#0F766E',
        },
        signal: {
          'sp': '#059669',
          's':  '#10B981',
          'a':  '#6EE7B7',
          'b':  '#FBBF24',
          'c':  '#FCA5A5',
          'd':  '#EF4444',
          'e':  '#DC2626',
        },
        market: {
          up:   '#EF4444',
          down: '#22C55E',
          flat: '#94A3B8',
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
    screens: {
      'sm': '640px',
      'md': '1024px',
      'lg': '1280px',
    },
  },
  plugins: [],
};
