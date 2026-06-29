/** @type {import('tailwindcss').Config} */
module.exports = {
  important: true,
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: ["selector"],
  theme: {
    extend: {
      colors: {
        // Autoppia brand orange as the primary accent.
        primary: "#E97C3C",
        "primary-strong": "#D2622C",
        secondary: "#FBFBFB",
        brand: "#E97C3C",
        accent2: "#F2A65C",
        success: "#58D68D",
        danger: "#EF5B5B",
        warning: "#F0B429",
        // Blue-tinted dark surfaces (from the hedge-fund / trading UIs).
        "dark-bg": "#070A10",
        "dark-surface": "#101620",
        "dark-surface-2": "#151D28",
        "dark-border": "#1F2A37",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],
        display: ['"Space Grotesk"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, #F08C4A, #D2622C)",
        "gradient-secondary": "linear-gradient(135deg, #F2A65C, #D2622C)",
        "gradient-glass": "linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05))",
      },
      boxShadow: {
        "soft": "0 2px 15px -3px rgba(0, 0, 0, 0.07), 0 10px 20px -2px rgba(0, 0, 0, 0.04)",
        "soft-lg": "0 10px 40px -10px rgba(0, 0, 0, 0.1)",
        "glow": "0 0 20px rgba(233, 124, 60, 0.18)",
        "glow-lg": "0 0 40px rgba(233, 124, 60, 0.24)",
        "inner-soft": "inset 0 2px 4px 0 rgba(0, 0, 0, 0.04)",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
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
