/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        charcoal: '#2C2A25',
        cream: '#F5F3EF',
        tan: '#8C7B5E',
        'tan-light': '#B5A892',
        'cream-dark': '#EAE6DF',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
