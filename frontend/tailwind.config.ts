import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#070A0E',
          900: '#0B0F14',
          850: '#10161D',
          800: '#151D26',
          700: '#1E2833',
          600: '#2B3846',
          500: '#3D4C5C',
        },
        accent: {
          DEFAULT: '#34D399',
          dim: '#10B981',
          soft: 'rgba(52, 211, 153, 0.12)',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
