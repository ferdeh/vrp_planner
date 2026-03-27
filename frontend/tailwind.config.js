/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#15385b",
        paper: "#f8faf8",
        accent: "#ea4a43",
        sea: "#0b73bf",
        sun: "#b8d211",
        petroblue: "#0b73bf",
        petrolime: "#b8d211",
        petrored: "#ea4a43",
        petroink: "#15385b",
        petrocloud: "#eef5f9"
      },
      fontFamily: {
        display: ["Arial", "Helvetica Neue", "sans-serif"],
        body: ["Arial", "Helvetica Neue", "sans-serif"]
      },
      boxShadow: {
        card: "0 18px 40px rgba(21, 56, 91, 0.10)"
      }
    }
  },
  plugins: []
};
