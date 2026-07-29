import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import App from "./App.jsx";
import "./index.css";

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (!CLERK_PUBLISHABLE_KEY) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

// Pulls from the same CSS custom properties as tailwind.config.js (see
// index.css :root) so Clerk's UI stays in sync with the app's theme —
// and with the STEGU brand manual, which --primary already matches
// exactly (#B71C2B).
const clerkAppearance = {
  variables: {
    colorPrimary: "hsl(var(--primary))",
    colorTextOnPrimaryBackground: "hsl(var(--primary-foreground))",
    colorBackground: "hsl(var(--card))",
    colorInputBackground: "hsl(var(--background))",
    colorText: "hsl(var(--foreground))",
    colorInputText: "hsl(var(--foreground))",
    colorTextSecondary: "hsl(var(--muted-foreground))",
    borderRadius: "var(--radius)",
    fontFamily: '"Inter", -apple-system, sans-serif',
  },
  elements: {
    card: "shadow-sm border border-border",
    formButtonPrimary: "hover:bg-[hsl(var(--primary-hover))]",
  },
};

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} appearance={clerkAppearance}>
      <App />
    </ClerkProvider>
  </React.StrictMode>
);
