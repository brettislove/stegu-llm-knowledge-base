import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import { dark } from "@clerk/themes";
import App from "./App.jsx";
import { applyTheme, getInitialTheme, subscribeTheme } from "./lib/theme.js";
import "./index.css";

// Applied before the first render so there's no flash of the wrong theme.
applyTheme(getInitialTheme());

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (!CLERK_PUBLISHABLE_KEY) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

// Pulls from the same CSS custom properties as tailwind.config.js (see
// index.css :root) so Clerk's UI stays in sync with the app's theme —
// and with the STEGU brand manual, which --primary already matches
// exactly (#B71C2B).
const clerkVariables = {
  colorPrimary: "hsl(var(--primary))",
  colorTextOnPrimaryBackground: "hsl(var(--primary-foreground))",
  colorBackground: "hsl(var(--card))",
  colorInputBackground: "hsl(var(--background))",
  colorText: "hsl(var(--foreground))",
  colorInputText: "hsl(var(--foreground))",
  colorTextSecondary: "hsl(var(--muted-foreground))",
  borderRadius: "var(--radius)",
  fontFamily: '"Inter", -apple-system, sans-serif',
};

const clerkElements = {
  card: "shadow-sm border border-border",
  formButtonPrimary: "hover:bg-[hsl(var(--primary-hover))]",
};

// Popovers (e.g. UserButton's menu in Sidebar.jsx) are portaled straight
// to document.body, so our HSL variables alone weren't enough — without
// an explicit dark baseTheme, Clerk falls back to its own light-mode
// defaults for anything the variables don't cover, rendering black text
// on our dark surfaces. baseTheme supplies a full matching palette that
// our variables then override on top of, same as in light mode.
function ClerkRoot() {
  const [theme, setThemeState] = useState(getInitialTheme);

  useEffect(() => subscribeTheme(setThemeState), []);

  const appearance = {
    baseTheme: theme === "dark" ? dark : undefined,
    variables: clerkVariables,
    elements: clerkElements,
  };

  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} appearance={appearance}>
      <App />
    </ClerkProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ClerkRoot />
  </React.StrictMode>
);
