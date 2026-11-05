// mistick API 客户端
const JSON_HEADERS = { "Content-Type": "application/json" };

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text.slice(0, 200) };
    }
  }
  if (!response.ok) {
    throw new Error(data.message || `HTTP ${response.status}`);
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  meta: () => request("/api/meta"),
  config: () => request("/api/config"),
  draws: (limit = 30, offset = 0) =>
    request(`/api/draws?limit=${limit}&offset=${offset}&order=desc`),
  stats: (window = "all") => request(`/api/stats?window=${encodeURIComponent(window)}`),
  sync: () => request("/api/sync", { method: "POST", headers: JSON_HEADERS, body: "{}" }),
  generate: (payload) =>
    request("/api/generate", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) }),
  backtest: (payload) =>
    request("/api/backtest", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) }),
  wheel: (payload) =>
    request("/api/wheel", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) }),
};