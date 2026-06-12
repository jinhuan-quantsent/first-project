/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sentiment: {
          extreme_fear: '#00A86B',    // 极度恐慌 - 绿
          fear: '#4CAF50',             // 恐慌 - 浅绿
          neutral: '#9E9E9E',          // 中性 - 灰
          greed: '#FF9800',            // 乐观 - 橙
          extreme_greed: '#F44336',    // 极度乐观 - 红
        },
        market: {
          up: '#F44336',       // 涨 - 红（A股习惯）
          down: '#4CAF50',     // 跌 - 绿
          flat: '#9E9E9E',
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
