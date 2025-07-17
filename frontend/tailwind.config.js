/** @type {import('tailwindcss').Config} */
module.exports = {
  important: true,
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: ["selector"],
  theme: {
    extend: {
      colors: {
        primary: "#FF996D",
        secondary: "#FBFBFB"
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(to right, #FF7E5F, #FEB47B)",
        "gradient-secondary": "linear-gradient(to right, #CB587E, #145CC2)"
      }
    },
  },
  plugins: [],
};


