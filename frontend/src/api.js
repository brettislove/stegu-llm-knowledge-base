const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  query: (question, mode) =>
    request("/query", { method: "POST", body: JSON.stringify({ question, mode }) }),

  // Updated to accept unified file_base64 parameter
  ingest: (filename, file_base64) =>
    request("/ingest", { method: "POST", body: JSON.stringify({ filename, file_base64 }) }),

  feedback: (question, bad_answer, correction) =>
    request("/feedback", {
      method: "POST",
      body: JSON.stringify({ question, bad_answer, correction }),
    }),

  distill: () => request("/distill", { method: "POST" }),

  lint: () => request("/lint", { method: "POST" }),

  listFiles: (subdir = "") =>
    request(`/wiki/files${subdir ? `?subdir=${encodeURIComponent(subdir)}` : ""}`),

  getFile: (path) => request(`/wiki/file?path=${encodeURIComponent(path)}`),
};

export function pdfToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}

export function readAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read file"));
    reader.readAsText(file);
  });
}