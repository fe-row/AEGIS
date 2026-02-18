/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        aegis: {
          50: '#f0f4ff', 100: '#dbe4ff', 200: '#bac8ff',
          500: '#4c6ef5', 600: '#3b5bdb', 700: '#364fc7',
          800: '#2b3d9e', 900: '#1e2a6e',
        },
      },
    },
  },
  plugins: [],
};