// REST client for the centinelas-pr universal intake FastAPI backend.
//
// Backend: server/backend/main.py
//   uvicorn server.backend.main:app --reload --port 8000  (from repo root)
//
// This is a SEPARATE client from appClient.js: the legislative pages use
// appClient (localStorage-backed, 21 civic entities); the universal 6-domain
// pipeline pages use this one (HTTP → FastAPI). The two data layers are
// intentionally independent.

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function getJSON(path, fallback = null) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return fallback;
    return await res.json();
  } catch (_error) {
    return fallback;
  }
}

const qs = (params = {}) => {
  const pairs = Object.entries(params).filter(([, v]) => v != null && v !== "");
  return pairs.length ? "?" + new URLSearchParams(pairs).toString() : "";
};

export const getHealth = () => getJSON("/health", { status: "down", counts: {} });
export const getItems = (filters = {}) => getJSON(`/items${qs(filters)}`, []);
export const getItem = (itemId) => getJSON(`/items/${encodeURIComponent(itemId)}`, null);
export const getQueue = () => getJSON("/queue", []);
export const getSources = () => getJSON("/sources", []);
export const getStatus = () => getJSON("/status", {});
