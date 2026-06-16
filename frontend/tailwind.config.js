/** @type {import('tailwindcss').Config} */
// Locked design tokens (see CLAUDE.md → Design tokens). Do not improvise colors.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Core palette
        ink: "#1B2430", // Midnight Brief
        canvas: "#F7F4EF", // Soft Oatmeal
        slate: "#475569",
        // Interactive / AI accent — fills, focus rings, citations only.
        marigold: "#D97706",
        // Severity (chips with colored left-border; never interactive).
        severity: {
          high: "#9B2C2C", // garnet
          medium: "#B5731A", // ochre
          low: "#4D7C6F", // sage
        },
      },
      fontFamily: {
        // Inter for all UI; Spectral for the wordmark only.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        wordmark: ["Spectral", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        // Subtle layered, navy-tinted shadows.
        card: "0 1px 2px rgba(27,36,48,0.06), 0 8px 24px rgba(27,36,48,0.08)",
        rail: "1px 0 0 rgba(27,36,48,0.10)",
      },
      backgroundImage: {
        // Recessed dark-navy "stage" with a radial wash for data viz.
        stage: "radial-gradient(120% 120% at 50% 0%, #243140 0%, #1B2430 60%, #141C26 100%)",
      },
    },
  },
  plugins: [],
};
