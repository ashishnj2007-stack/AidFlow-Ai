const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
export async function api(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || body.error || `Request failed (${res.status})`);
  return body;
}
