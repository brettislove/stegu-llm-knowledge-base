// Tailwind's darkMode:["class"] means a .dark class on <html> is what
// actually switches every token in index.css — nothing applies that class
// on its own, so this (+ the toggle button in Sidebar.jsx) is what makes
// dark mode reachable at all.
const STORAGE_KEY = "stegu-kb-theme";
const THEME_EVENT = "stegu-theme-change";

export function getInitialTheme() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function setTheme(theme) {
  localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
  // ClerkProvider's appearance (main.jsx) needs to react to toggles too —
  // its popovers are portaled to document.body, outside React's normal
  // prop flow from ThemeToggle's own local state, and without a matching
  // Clerk baseTheme they keep light-mode (black-on-dark) text.
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function subscribeTheme(callback) {
  function handler(e) {
    callback(e.detail);
  }
  window.addEventListener(THEME_EVENT, handler);
  return () => window.removeEventListener(THEME_EVENT, handler);
}
