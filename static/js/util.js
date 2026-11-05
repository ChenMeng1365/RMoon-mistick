// 通用工具
export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const zero = (n) => String(n).padStart(2, "0");

export function comb(n, k) {
  if (k < 0 || k > n) return 0;
  let result = 1;
  for (let i = 1; i <= k; i += 1) {
    result = (result * (n - k + i)) / i;
  }
  return Math.round(result);
}

export function combinations(items, k) {
  const out = [];
  const pick = (start, current) => {
    if (current.length === k) {
      out.push([...current]);
      return;
    }
    for (let i = start; i < items.length; i += 1) {
      current.push(items[i]);
      pick(i + 1, current);
      current.pop();
    }
  };
  pick(0, []);
  return out;
}

export function money(value) {
  return `¥${Number(value || 0).toLocaleString("zh-CN")}`;
}

export function shortTime(ts) {
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

let toastTimer = null;
export function toast(message, type = "info") {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.className = `toast show ${type === "error" ? "err" : type === "ok" ? "ok" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = "toast";
  }, 2400);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`已复制：${text}`, "ok");
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      toast(`已复制：${text}`, "ok");
    } finally {
      area.remove();
    }
  }
}

export function prizeLevel(reds, blue, draw) {
  if (!draw) return 0;
  const actualReds = String(draw.r).split(",").map(Number);
  const hitRed = reds.filter((n) => actualReds.includes(n)).length;
  const hitBlue = Number(blue) === Number(draw.b);
  if (hitRed === 6 && hitBlue) return 1;
  if (hitRed === 6) return 2;
  if (hitRed === 5 && hitBlue) return 3;
  if (hitRed === 5 || (hitRed === 4 && hitBlue)) return 4;
  if (hitRed === 4 || (hitRed === 3 && hitBlue)) return 5;
  if (hitBlue && hitRed <= 2) return 6;
  return 0;
}

export const PRIZE_NAMES = {
  1: "一等奖",
  2: "二等奖",
  3: "三等奖",
  4: "四等奖",
  5: "五等奖",
  6: "六等奖",
};

export function download(filename, text, mime = "application/json") {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function parseNumberList(text) {
  return String(text || "")
    .split(/[,\s，、]+/)
    .map((x) => Number(x))
    .filter((x) => Number.isInteger(x));
}

export function fmtP(value) {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 0.001) return "<0.001";
  return Number(value).toFixed(4);
}

export function pct(value, digits = 1) {
  return `${(Number(value || 0) * 100).toFixed(digits)}%`;
}