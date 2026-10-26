/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#070a12",
          900: "#0b0f19",
          800: "#111827",
          700: "#1e293b",
          600: "#334155",
        },
      },
    },
  },
  plugins: [],
};
