/** @type {import('tailwindcss').Config} */
module.exports = {
  important: true,
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: ["selector"],
  theme: {
    extend: {
      colors: {
        primary: "rgb(var(--color-primary) / <alpha-value>)",
        "primary-strong": "rgb(var(--color-primary-strong) / <alpha-value>)",
        secondary: "#FBFBFB",
        brand: "rgb(var(--color-primary) / <alpha-value>)",
        accent2: "rgb(var(--color-accent-2) / <alpha-value>)",
        success: "#58D68D",
        danger: "#EF5B5B",
        warning: "#F0B429",
        // Blue-tinted dark surfaces (lightened from near-black for a calmer,
        // less heavy dark mode).
        "dark-bg": "#12161F",
        "dark-surface": "#1A1F2B",
        "dark-surface-2": "#232A38",
        "dark-border": "#2B3443",
      },
      fontFamily: {
        sans: ["var(--sans)"],
        display: ["var(--display)"],
        mono: ["var(--mono)"],
      },
      backgroundImage: {
        "gradient-primary": "var(--brand-bg)",
        "gradient-secondary": "linear-gradient(135deg, rgb(var(--color-accent-2)), rgb(var(--color-primary-strong)))",
        "gradient-glass": "linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05))",
      },
      boxShadow: {
        "soft": "0 2px 15px -3px rgba(0, 0, 0, 0.07), 0 10px 20px -2px rgba(0, 0, 0, 0.04)",
        "soft-lg": "0 10px 40px -10px rgba(0, 0, 0, 0.1)",
        "glow": "var(--glow)",
        "glow-lg": "var(--glow-lg)",
        "inner-soft": "inset 0 2px 4px 0 rgba(0, 0, 0, 0.04)",
      },
      borderRadius: {
        "2xl": "calc(var(--radius) + 3px)",
        "3xl": "calc(var(--radius) + 11px)",
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out",
        "slide-up": "slideUp 0.5s ease-out",
        "slide-in-right": "slideInRight 0.3s ease-out",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
        "shimmer-slide": "shimmerSlide 1.7s ease-in-out infinite",
      },
      keyframes: {
        shimmerSlide: {
          "0%": { transform: "translateX(-130%)" },
          "100%": { transform: "translateX(130%)" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { opacity: "0", transform: "translateX(20px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
