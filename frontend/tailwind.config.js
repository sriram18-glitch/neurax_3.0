/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-2": "var(--bg-2)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        "panel-2": "rgb(var(--panel-2) / <alpha-value>)",
        line: "rgb(var(--line) / 0.14)",
        "line-2": "rgb(var(--line-2) / 0.28)",
        ink: "var(--text)",
        "ink-2": "var(--text-2)",
        "ink-3": "var(--text-3)",
        cyan: "rgb(var(--cyan) / <alpha-value>)",
        ok: "rgb(var(--green) / <alpha-value>)",
        warn: "rgb(var(--amber) / <alpha-value>)",
        bad: "rgb(var(--red) / <alpha-value>)",
        novel: "rgb(var(--violet) / <alpha-value>)",
        idle: "rgb(var(--slate) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem", letterSpacing: "0.08em" }],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 12px 32px -24px rgba(0,0,0,0.9)",
        lift: "0 24px 48px -24px rgba(0,0,0,0.85)",
      },
      transitionTimingFunction: {
        industrial: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
