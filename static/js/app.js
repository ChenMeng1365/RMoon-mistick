// mistick 前端主逻辑
import { api } from "./api.js";
import { barChart, hBars, sparkline, heatmap } from "./charts.js";
import {
  $,
  $$,
  zero,
  comb,
  combinations,
  money,
  toast,
  copyText,
  prizeLevel,
  PRIZE_NAMES,
  download,
  parseNumberList,
  fmtP,
  pct,
} from "./util.js";

const RECORDS_KEY = "mistick.records.v2";
const LEGACY_KEY = "mistick-ssq-recs";
const MAX_RECORDS = 500;

const MODE_LABELS = {
  single: "单式",
  multiple: "复式",
  dantuo: "胆拖",
  smart: "策略",
};

const state = {
  config: null,
  meta: null,
  recent: [],
  latest: null,
  mode: "single",
  red: new Set(),
  blue: new Set(),
  dan: new Set(),
  editSet: "drag",
  records: [],
  statsWindow: "all",
  statsTab: "overview",
  stats: null,
  statsCache: new Map(),
  lastGen: [],
  genStrategy: "random",
  genStrategyName: "纯随机",
  wheelTickets: [],
  backtestResult: null,
};

// ========== 初始化 ==========
document.addEventListener("DOMContentLoaded", init);

function init() {
  buildBalls();
  populateWheelBlue();
  bindEvents();
  loadRecords();
  renderSelection();
  renderRecords();
  loadConfig();
  loadData();
  loadStats();
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

async function loadConfig() {
  try {
    state.config = await api.config();
    fillStrategySelects();
  } catch (error) {
    toast(`配置加载失败：${error.message}`, "error");
    state.config = { strategies: defaultStrategies(), limits: {} };
    fillStrategySelects();
  }
}

function defaultStrategies() {
  return [
    { id: "random", name: "纯随机" },
    { id: "hot", name: "热号跟随" },
    { id: "cold", name: "冷号回补" },
    { id: "omission", name: "遗漏回补" },
    { id: "balanced", name: "均衡形态" },
    { id: "avoid", name: "避开热门" },
    { id: "custom", name: "自定义过滤" },
  ];
}

function fillStrategySelects() {
  const list = state.config?.strategies || defaultStrategies();
  const options = list.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
  const select = $("#strategySel");
  if (select) {
    select.innerHTML = options;
    select.value = state.genStrategy;
  }
}

async function loadData() {
  try {
    const [meta, draws] = await Promise.all([api.meta(), api.draws(30)]);
    state.meta = meta;
    state.recent = draws.items || [];
    state.latest = state.recent[0] || null;
    renderDraws();
    renderRecords();
    updateStatus(true, `服务正常 · ${meta.count} 期`);
  } catch (error) {
    updateStatus(false, "服务离线");
    toast(`数据加载失败：${error.message}`, "error");
    renderDraws();
  }
}

async function refreshHealth() {
  try {
    const health = await api.health();
    updateStatus(true, `服务正常 · ${health.draws} 期`);
  } catch {
    updateStatus(false, "服务离线");
  }
}

function updateStatus(ok, text) {
  const el = $("#status");
  if (!el) return;
  el.className = `status ${ok ? "ok" : "err"}`;
  const label = el.querySelector("span");
  if (label) label.textContent = text;
}

// ========== 选号 ==========
function buildBalls() {
  const redBox = $("#redBalls");
  for (let n = 1; n <= 33; n += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ball";
    button.dataset.n = String(n);
    button.textContent = zero(n);
    button.addEventListener("click", () => toggleRed(n));
    redBox.appendChild(button);
  }
  const blueBox = $("#blueBalls");
  for (let n = 1; n <= 16; n += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ball";
    button.dataset.n = String(n);
    button.textContent = zero(n);
    button.addEventListener("click", () => toggleBlue(n));
    blueBox.appendChild(button);
  }
}

function toggleRed(n) {
  if (state.mode === "smart") return;
  if (state.mode === "single") {
    if (state.red.has(n)) {
      state.red.delete(n);
    } else if (state.red.size >= 6) {
      toast("单式红球最多 6 个，切到复式可选更多", "error");
      return;
    } else {
      state.red.add(n);
    }
  } else if (state.mode === "multiple") {
    if (state.red.has(n)) {
      state.red.delete(n);
    } else if (state.red.size >= 20) {
      toast("复式红球最多 20 个", "error");
      return;
    } else {
      state.red.add(n);
    }
  } else if (state.mode === "dantuo") {
    if (state.editSet === "dan") {
      if (state.dan.has(n)) {
        state.dan.delete(n);
      } else if (state.dan.size >= 5) {
        toast("胆码最多 5 个", "error");
        return;
      } else {
        state.dan.add(n);
        state.red.delete(n);
      }
    } else if (state.red.has(n)) {
      state.red.delete(n);
    } else if (state.red.size + state.dan.size >= 20) {
      toast("胆拖红球合计最多 20 个", "error");
      return;
    } else {
      state.red.add(n);
      state.dan.delete(n);
    }
  }
  renderSelection();
}

function toggleBlue(n) {
  if (state.mode === "smart") return;
  if (state.mode === "single") {
    if (state.blue.has(n)) {
      state.blue.delete(n);
    } else {
      state.blue.clear();
      state.blue.add(n);
    }
  } else if (state.blue.has(n)) {
    state.blue.delete(n);
  } else if (state.blue.size >= 16) {
    toast("蓝球最多 16 个", "error");
  } else {
    state.blue.add(n);
  }
  renderSelection();
}

function renderBalls() {
  $$("#redBalls .ball").forEach((ball) => {
    const n = Number(ball.dataset.n);
    ball.classList.toggle("on-red", state.red.has(n));
    ball.classList.toggle("on-dan", state.dan.has(n));
    ball.classList.toggle("dim", isRedDim(n));
  });
  $$("#blueBalls .ball").forEach((ball) => {
    const n = Number(ball.dataset.n);
    ball.classList.toggle("on-blue", state.blue.has(n));
    ball.classList.toggle("dim", isBlueDim(n));
  });
}

function isRedDim(n) {
  if (state.mode === "single") return state.red.size >= 6 && !state.red.has(n);
  if (state.mode === "multiple") return state.red.size >= 20 && !state.red.has(n);
  if (state.mode === "dantuo") {
    if (state.editSet === "dan") return state.dan.size >= 5 && !state.dan.has(n);
    return state.red.size + state.dan.size >= 20 && !state.red.has(n);
  }
  return false;
}

function isBlueDim(n) {
  if (state.mode === "single") return state.blue.size >= 1 && !state.blue.has(n);
  return state.blue.size >= 16 && !state.blue.has(n);
}

function computeTickets() {
  if (state.mode === "single") {
    return state.red.size === 6 && state.blue.size >= 1 ? 1 : 0;
  }
  if (state.mode === "multiple") {
    return state.red.size >= 6 && state.blue.size >= 1 ? comb(state.red.size, 6) * state.blue.size : 0;
  }
  if (state.mode === "dantuo") {
    const need = 6 - state.dan.size;
    if (state.dan.size < 1 || need < 0 || state.red.size < need || state.blue.size < 1) return 0;
    if (state.dan.size + state.red.size > 20) return 0;
    return comb(state.red.size, need) * state.blue.size;
  }
  return 0;
}

function expandTickets() {
  const blue = [...state.blue].sort((a, b) => a - b);
  if (state.mode === "single") {
    return state.red.size === 6 && blue.length
      ? [{ r: [...state.red].sort((a, b) => a - b), b: blue[0] }]
      : [];
  }
  if (state.mode === "multiple") {
    if (state.red.size < 6 || !blue.length) return [];
    return combinations([...state.red].sort((a, b) => a - b), 6).flatMap((reds) =>
      blue.map((b) => ({ r: reds, b })),
    );
  }
  if (state.mode === "dantuo") {
    const need = 6 - state.dan.size;
    if (state.dan.size < 1 || need < 0 || state.red.size < need || !blue.length) return [];
    const dan = [...state.dan].sort((a, b) => a - b);
    return combinations([...state.red].sort((a, b) => a - b), need).flatMap((drag) => {
      const reds = [...dan, ...drag].sort((a, b) => a - b);
      return blue.map((b) => ({ r: reds, b }));
    });
  }
  return [];
}

function renderSelection() {
  renderBalls();
  const tickets = computeTickets();
  const redCount = $("#redCount");
  const blueCount = $("#blueCount");
  const ticketMeta = $("#ticketMeta");
  const modeHint = $("#modeHint");
  const saveBtn = $("#saveBtn");

  if (state.mode === "dantuo") {
    redCount.textContent = `${state.dan.size} 胆 + ${state.red.size} 拖`;
  } else if (state.mode === "multiple") {
    redCount.textContent = `${state.red.size}/20`;
  } else {
    redCount.textContent = `${state.red.size}/6`;
  }
  blueCount.textContent = `${state.blue.size}/${state.mode === "single" ? 1 : 16}`;

  const box = $("#selection");
  box.innerHTML = "";
  const reds = [...state.red].sort((a, b) => a - b);
  const dans = [...state.dan].sort((a, b) => a - b);
  const blues = [...state.blue].sort((a, b) => a - b);
  if (!reds.length && !dans.length && !blues.length) {
    const placeholder = document.createElement("span");
    placeholder.className = "placeholder";
    placeholder.textContent =
      state.mode === "smart" ? "切到单式 / 复式 / 胆拖开始选号" : "点击号码开始选号";
    box.appendChild(placeholder);
  }
  dans.forEach((n) => box.appendChild(numberChip(n, "dan")));
  reds.forEach((n) => box.appendChild(numberChip(n, "red")));
  blues.forEach((n) => box.appendChild(numberChip(n, "blue")));

  ticketMeta.textContent = `${tickets} 注 · ${money(tickets * 2)}`;
  modeHint.textContent = {
    single: "单式：红球 6 个，蓝球 1 个",
    multiple: "复式：红球 7–20 个，蓝球 1–16 个",
    dantuo: "胆拖：胆码 1–5 个，拖码补足 6 个；红球合计 ≤20",
    smart: "策略生成：按历史分布采样，可附加硬过滤",
  }[state.mode];
  saveBtn.disabled = !tickets || tickets > MAX_RECORDS;
  saveBtn.textContent = tickets > MAX_RECORDS ? `注数过多（${tickets}）` : "存入注单";
  $("#dantuoSwitch").hidden = state.mode !== "dantuo";
  $$("#dantuoSwitch button").forEach((button) => {
    button.classList.toggle("on", button.dataset.set === state.editSet);
  });
}

function numberChip(n, kind) {
  const chip = document.createElement("span");
  chip.className = `chip-num ${kind}`;
  chip.textContent = zero(n);
  return chip;
}

function switchMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  state.red.clear();
  state.blue.clear();
  state.dan.clear();
  state.editSet = "drag";
  $$("#modeTabs .tab").forEach((tab) => tab.classList.toggle("on", tab.dataset.mode === mode));
  $("#manualPane").hidden = mode === "smart";
  $("#smartPane").hidden = mode !== "smart";
  renderSelection();
}

function randomFill() {
  const sample = (count, max, exclude = new Set()) => {
    const pool = [];
    for (let n = 1; n <= max; n += 1) if (!exclude.has(n)) pool.push(n);
    for (let i = pool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, count).sort((a, b) => a - b);
  };
  state.red.clear();
  state.blue.clear();
  state.dan.clear();
  if (state.mode === "single") {
    sample(6, 33).forEach((n) => state.red.add(n));
    state.blue.add(sample(1, 16)[0]);
  } else if (state.mode === "multiple") {
    sample(7 + Math.floor(Math.random() * 3), 33).forEach((n) => state.red.add(n));
    sample(1 + Math.floor(Math.random() * 2), 16).forEach((n) => state.blue.add(n));
  } else if (state.mode === "dantuo") {
    const dan = sample(2, 33);
    dan.forEach((n) => state.dan.add(n));
    sample(7, 33, new Set(dan)).forEach((n) => state.red.add(n));
    state.blue.add(sample(1, 16)[0]);
  } else {
    return;
  }
  renderSelection();
}

function clearSelection() {
  state.red.clear();
  state.blue.clear();
  state.dan.clear();
  state.editSet = "drag";
  renderSelection();
}

function saveSelection() {
  const total = computeTickets();
  if (!total) {
    toast("请先选够号码", "error");
    return;
  }
  if (total > MAX_RECORDS) {
    toast(`单次最多存 ${MAX_RECORDS} 注，当前 ${total} 注`, "error");
    return;
  }
  const tickets = expandTickets();
  addRecords(tickets, MODE_LABELS[state.mode], MODE_LABELS[state.mode]);
  clearSelection();
  toast(`已存入 ${tickets.length} 注，${money(tickets.length * 2)}`, "ok");
}

// ========== 注单 ==========
function loadRecords() {
  let raw = localStorage.getItem(RECORDS_KEY);
  if (!raw) raw = localStorage.getItem(LEGACY_KEY);
  let list = [];
  try {
    list = JSON.parse(raw || "[]");
  } catch {
    list = [];
  }
  if (!Array.isArray(list)) list = [];
  state.records = list
    .map((item) => normalizeRecord(item))
    .filter(Boolean)
    .slice(-MAX_RECORDS);
  persistRecords();
}

function normalizeRecord(item) {
  if (!item || !Array.isArray(item.r) || item.r.length !== 6) return null;
  const reds = item.r.map(Number).filter((n) => Number.isInteger(n) && n >= 1 && n <= 33);
  const blue = Number(item.b);
  if (reds.length !== 6 || !Number.isInteger(blue) || blue < 1 || blue > 16) return null;
  return {
    id: item.id || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    r: reds.sort((a, b) => a - b),
    b: blue,
    t: Number(item.t) || Date.now(),
    s: item.s || "legacy",
    label: item.label || "历史",
    tags: Array.isArray(item.tags) ? item.tags : [],
  };
}

function persistRecords() {
  try {
    localStorage.setItem(RECORDS_KEY, JSON.stringify(state.records.slice(-MAX_RECORDS)));
  } catch {
    toast("本地存储写入失败", "error");
  }
}

function addRecords(tickets, strategyId, label, tags = []) {
  if (tickets.length > MAX_RECORDS) {
    toast(`单次最多存 ${MAX_RECORDS} 注，当前 ${tickets.length} 注`, "error");
    return false;
  }
  const now = Date.now();
  const records = tickets.map((ticket, index) => ({
    id: `${now.toString(36)}-${index}-${Math.random().toString(36).slice(2, 6)}`,
    r: [...ticket.r],
    b: Number(ticket.b),
    t: now + index,
    s: strategyId,
    label: label || strategyId,
    tags: ticket.tags || tags,
  }));
  state.records = [...state.records, ...records].slice(-MAX_RECORDS);
  persistRecords();
  renderRecords();
}

function renderRecords() {
  const box = $("#records");
  box.innerHTML = "";
  const count = state.records.length;
  $("#recCount").textContent = `${count} 注 · ${money(count * 2)}`;
  if (!count) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "暂无注单，选一注或让策略生成";
    box.appendChild(empty);
    return;
  }
  [...state.records].reverse().forEach((record, index) => {
    const row = document.createElement("div");
    row.className = "record";
    row.title = "点击复制号码";

    const idx = document.createElement("span");
    idx.className = "idx";
    idx.textContent = `#${String(count - index).padStart(3, "0")}`;

    const nums = document.createElement("span");
    nums.className = "nums";
    const red = document.createElement("span");
    red.className = "r";
    red.textContent = record.r.map(zero).join(" ");
    const blue = document.createElement("span");
    blue.className = "b";
    blue.textContent = zero(record.b);
    nums.append(red, blue);

    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = record.label || MODE_LABELS[record.s] || "自定义";

    const level = state.latest ? prizeLevel(record.r, record.b, state.latest) : 0;
    const hit = document.createElement("span");
    hit.className = `hit ${level ? "win" : ""}`;
    hit.textContent = state.latest ? (level ? PRIZE_NAMES[level] : "未中") : "待校验";

    const del = document.createElement("button");
    del.type = "button";
    del.className = "del";
    del.textContent = "×";
    del.title = "删除此注";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      state.records = state.records.filter((item) => item.id !== record.id);
      persistRecords();
      renderRecords();
    });

    row.append(idx, nums, tag, hit, del);
    row.addEventListener("click", () =>
      copyText(`${record.r.map(zero).join(" ")} + ${zero(record.b)}`),
    );
    box.appendChild(row);
  });
}

function clearRecords() {
  if (!state.records.length) {
    toast("注单已经是空的");
    return;
  }
  if (!confirm(`确认清空全部 ${state.records.length} 注？`)) return;
  state.records = [];
  persistRecords();
  renderRecords();
  toast("注单已清空");
}

function exportRecords() {
  if (!state.records.length) {
    toast("没有可导出的注单", "error");
    return;
  }
  const payload = {
    app: "mistick",
    exportedAt: new Date().toISOString(),
    count: state.records.length,
    records: state.records,
  };
  download(`mistick-records-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(payload, null, 2));
  toast(`已导出 ${state.records.length} 注`, "ok");
}

// ========== 开奖 ==========
function renderDraws() {
  const box = $("#draws");
  box.innerHTML = "";
  const meta = $("#drawMeta");
  if (meta) meta.textContent = state.meta ? `库 ${state.meta.count} 期` : "—";
  if (!state.recent.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "尚无开奖数据，点击「同步数据」";
    box.appendChild(empty);
    return;
  }
  state.recent.forEach((draw) => {
    const row = document.createElement("div");
    row.className = "draw";
    row.title = "点击复制开奖号码";

    const no = document.createElement("span");
    no.className = "no";
    no.textContent = draw.c;

    const nums = document.createElement("span");
    nums.className = "nums";
    const red = document.createElement("span");
    red.className = "r";
    red.textContent = String(draw.r).split(",").join(" ");
    const blue = document.createElement("span");
    blue.className = "b";
    blue.textContent = draw.b;
    nums.append(red, blue);

    const date = document.createElement("span");
    date.className = "date";
    date.textContent = draw.d;

    const pool = document.createElement("span");
    pool.className = "pool";
    pool.textContent = draw.p ? `${(Number(draw.p) / 1e8).toFixed(2)}亿` : "";

    row.append(no, nums, date, pool);
    row.addEventListener("click", () =>
      copyText(`${String(draw.r).split(",").join(" ")} + ${draw.b}`),
    );
    box.appendChild(row);
  });
}

async function syncData() {
  const button = $("#syncBtn");
  button.disabled = true;
  button.classList.add("loading");
  try {
    const result = await api.sync();
    const warn = result.errors?.length ? `；警告：${result.errors.join("；")}` : "";
    toast(`同步完成：${result.count} 期，新增 ${result.added} 期${warn}`, "ok");
    state.statsCache.clear();
    await loadData();
    await loadStats(true);
  } catch (error) {
    toast(`同步失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

// ========== 统计 ==========
async function loadStats(force = false) {
  const window = state.statsWindow;
  if (!force && state.statsCache.has(window)) {
    state.stats = state.statsCache.get(window);
    renderStats();
    return;
  }
  const body = $("#statBody");
  body.innerHTML = '<div class="empty">统计计算中…</div>';
  try {
    const data = await api.stats(window);
    state.statsCache.set(window, data);
    state.stats = data;
    renderStats();
  } catch (error) {
    body.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = `统计加载失败：${error.message}`;
    body.appendChild(empty);
  }
}

function renderStats() {
  const body = $("#statBody");
  body.innerHTML = "";
  if (state.statsTab === "backtest") {
    renderBacktest();
    return;
  }
  if (!state.stats) {
    body.innerHTML = '<div class="empty">统计计算中…</div>';
    return;
  }
  const renderers = {
    overview: renderOverview,
    shape: renderShape,
    omission: renderOmission,
    relation: renderRelation,
    test: renderTest,
  };
  (renderers[state.statsTab] || renderOverview)(body, state.stats);
}

function card(title, sub = "") {
  const el = document.createElement("div");
  el.className = "card";
  const h = document.createElement("h3");
  h.textContent = title;
  el.appendChild(h);
  if (sub) {
    const p = document.createElement("div");
    p.className = "sub";
    p.textContent = sub;
    el.appendChild(p);
  }
  return el;
}

function cardGrid(className = "cards") {
  const grid = document.createElement("div");
  grid.className = className;
  return grid;
}

function addCards(body, cards, className = "cards") {
  const grid = cardGrid(className);
  cards.forEach((item) => grid.appendChild(item));
  body.appendChild(grid);
  return grid;
}

function renderOverview(body, s) {
  const strip = document.createElement("div");
  strip.className = "summary-strip";
  const items = [
    `样本 <b>${s.n}</b> 期`,
    `${s.range.first || "—"} ~ ${s.range.last || "—"}`,
    `和值均值 <b>${s.sum.mean}</b>`,
    `跨度均值 <b>${s.span.mean}</b>`,
    `AC 均值 <b>${s.ac.mean}</b>`,
    `红球 χ² <b>${s.red.chi2}</b> p=<b>${fmtP(s.red.p)}</b>`,
  ];
  items.forEach((text) => {
    const span = document.createElement("span");
    span.innerHTML = text;
    strip.appendChild(span);
  });
  body.appendChild(strip);

  const cards = [];
  const redCard = card("红球频次", `期望 ${s.red.expected} 次 / 号 · 共 ${s.n} 期`);
  const redBox = document.createElement("div");
  redCard.appendChild(redBox);
  barChart(
    redBox,
    Array.from({ length: 33 }, (_, i) => {
      const n = i + 1;
      return {
        label: zero(n),
        value: s.red.counts[n],
        title: `红 ${zero(n)}：${s.red.counts[n]} 次`,
      };
    }),
    { color: "red" },
  );
  cards.push(redCard);

  const blueCard = card("蓝球频次", `期望 ${s.blue.expected} 次 / 号`);
  const blueBox = document.createElement("div");
  blueCard.appendChild(blueBox);
  barChart(
    blueBox,
    Array.from({ length: 16 }, (_, i) => {
      const n = i + 1;
      return {
        label: zero(n),
        value: s.blue.counts[n],
        title: `蓝 ${zero(n)}：${s.blue.counts[n]} 次`,
      };
    }),
    { color: "blue" },
  );
  cards.push(blueCard);

  const sumCard = card("和值分布", `均值 ${s.sum.mean} · 标准差 ${s.sum.std} · 范围 ${s.sum.min}–${s.sum.max}`);
  const sumBox = document.createElement("div");
  sumCard.appendChild(sumBox);
  hBars(sumBox, s.sum.buckets, { total: s.n });
  cards.push(sumCard);

  const trendCard = card("和值走势", "最近 30 期");
  const trendBox = document.createElement("div");
  trendCard.appendChild(trendBox);
  sparkline(trendBox, s.sum.recent, { color: "#22d3ee" });
  cards.push(trendCard);

  const oddCard = card("奇偶比", "红球奇数个数");
  const oddBox = document.createElement("div");
  oddCard.appendChild(oddBox);
  hBars(oddBox, s.odd, { total: s.n });
  cards.push(oddCard);

  const bigCard = card("大小比", "小 ≤16，大 ≥17");
  const bigBox = document.createElement("div");
  bigCard.appendChild(bigBox);
  hBars(bigBox, s.big, { total: s.n });
  cards.push(bigCard);

  const zoneCard = card("三区比", "一区 1–11 / 二区 12–22 / 三区 23–33");
  const zoneBox = document.createElement("div");
  zoneCard.appendChild(zoneBox);
  hBars(zoneBox, s.zone, { total: s.n, limit: 8 });
  cards.push(zoneCard);

  const blueShapeCard = card("蓝球形态", "大小 / 奇偶 / 012 路");
  const blueShapeBox = document.createElement("div");
  blueShapeCard.appendChild(blueShapeBox);
  const blueBig = document.createElement("div");
  blueBig.style.marginBottom = "8px";
  hBars(blueBig, s.blueShape.big, { total: s.n, color: "blue" });
  const blueOdd = document.createElement("div");
  blueOdd.style.marginBottom = "8px";
  hBars(blueOdd, s.blueShape.odd, { total: s.n, color: "blue" });
  const blueRoad = document.createElement("div");
  hBars(blueRoad, s.blueShape.road, { total: s.n, color: "blue" });
  blueShapeBox.append(blueBig, blueOdd, blueRoad);
  cards.push(blueShapeCard);

  addCards(body, cards);
}

function renderShape(body, s) {
  const cards = [];
  const spanCard = card("跨度", `均值 ${s.span.mean} · 最大号 - 最小号`);
  const spanBox = document.createElement("div");
  spanCard.appendChild(spanBox);
  hBars(spanBox, s.span.buckets, { total: s.n });
  cards.push(spanCard);

  const acCard = card("AC 值", `均值 ${s.ac.mean} · 两两差值去重数 - 5`);
  const acBox = document.createElement("div");
  acCard.appendChild(acBox);
  hBars(acBox, s.ac.buckets, { total: s.n });
  cards.push(acCard);

  const primeCard = card("质合比", "质数：2,3,5,7,11,13,17,19,23,29,31");
  const primeBox = document.createElement("div");
  primeCard.appendChild(primeBox);
  hBars(primeBox, s.prime, { total: s.n });
  cards.push(primeCard);

  const roadCard = card("012 路", "红球除 3 余数分布，展示前 8");
  const roadBox = document.createElement("div");
  roadCard.appendChild(roadBox);
  hBars(roadBox, s.road, { total: s.n, limit: 8 });
  cards.push(roadCard);

  const tailCard = card("尾数分布", "每个尾数在所有红球中的出现次数");
  const tailBox = document.createElement("div");
  tailCard.appendChild(tailBox);
  barChart(
    tailBox,
    s.tail.counts.map((value, index) => ({ label: String(index), value, title: `尾 ${index}：${value} 次` })),
    { showValue: true },
  );
  cards.push(tailCard);

  const sameTailCard = card("同尾组数", "一期中重复尾数的组数");
  const sameTailBox = document.createElement("div");
  sameTailCard.appendChild(sameTailBox);
  hBars(sameTailBox, s.tail.same, { total: s.n });
  cards.push(sameTailCard);

  const consecutiveCard = card("连号", "相邻号码对的个数");
  const consecutiveBox = document.createElement("div");
  consecutiveCard.appendChild(consecutiveBox);
  hBars(consecutiveBox, s.consecutive, { total: s.n });
  cards.push(consecutiveCard);

  const repeatCard = card("重号", "与上期相同的红球个数");
  const repeatBox = document.createElement("div");
  repeatCard.appendChild(repeatBox);
  const repeatTotal = s.repeat.reduce((sum, item) => sum + item.n, 0);
  hBars(repeatBox, s.repeat, { total: repeatTotal });
  cards.push(repeatCard);

  const neighborCard = card("邻号", "与上期红球相差 1 的个数");
  const neighborBox = document.createElement("div");
  neighborCard.appendChild(neighborBox);
  const neighborTotal = s.neighbor.reduce((sum, item) => sum + item.n, 0);
  hBars(neighborBox, s.neighbor, { total: neighborTotal });
  cards.push(neighborCard);

  const blueTailCard = card("蓝球尾数", "蓝球个位分布");
  const blueTailBox = document.createElement("div");
  blueTailCard.appendChild(blueTailBox);
  barChart(
    blueTailBox,
    s.blueShape.tail.map((item) => ({ label: item.key, value: item.n, title: `尾 ${item.key}：${item.n} 次` })),
    { color: "blue", showValue: true },
  );
  cards.push(blueTailCard);

  addCards(body, cards, "cards three");
}

function renderOmission(body, s) {
  const grid = cardGrid();
  const redCard = card("红球遗漏", "按当前遗漏从大到小排序");
  redCard.appendChild(omissionTable(s, "red", 33));
  grid.appendChild(redCard);

  const blueCard = card("蓝球遗漏", "按当前遗漏从大到小排序");
  blueCard.appendChild(omissionTable(s, "blue", 16));
  grid.appendChild(blueCard);
  body.appendChild(grid);

  const note = document.createElement("div");
  note.className = "card";
  note.style.marginTop = "12px";
  note.innerHTML = '<h3>口径说明</h3><div class="note">当前遗漏 = 从最新一期往回数，连续未出现的期数；平均遗漏 = 总期数 / 出现次数 - 1；最大遗漏 = 历史最长连续未出期数（含当前）。遗漏只描述过去，不构成“该出了”的理由。</div>';
  body.appendChild(note);
}

function omissionTable(s, kind, max) {
  const data = s[kind];
  const rows = [];
  for (let n = 1; n <= max; n += 1) {
    rows.push({
      n,
      current: data.omission.current[n],
      avg: data.omission.avg[n],
      max: data.omission.max[n],
      count: data.counts[n],
    });
  }
  rows.sort((a, b) => b.current - a.current || a.n - b.n);
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>号码</th><th>当前</th><th>平均</th><th>最大</th><th>出现</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    if (index < 5) tr.className = "hot";
    tr.innerHTML = `<td>${kind === "red" ? "红" : "蓝"} ${zero(row.n)}</td><td>${row.current}</td><td>${row.avg}</td><td>${row.max}</td><td>${row.count}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function renderRelation(body, s) {
  const grid = document.createElement("div");
  grid.className = "relation-grid";

  const heatCard = card("号码共现热力图", "33×33，颜色越亮表示同期出现次数越多");
  const heatBox = document.createElement("div");
  heatBox.className = "heatmap-wrap";
  heatCard.appendChild(heatBox);
  heatmap(heatBox, s.cooccurrence.matrix, { max: s.cooccurrence.max });
  grid.appendChild(heatCard);

  const topCard = card("高频号码对", "同一期同时出现的次数");
  const topBox = document.createElement("div");
  topCard.appendChild(topBox);
  s.cooccurrence.top.forEach((pair, index) => {
    const row = document.createElement("div");
    row.className = "pair-row";
    row.innerHTML = `<span class="pn">${zero(pair.a)} + ${zero(pair.b)}</span><span class="pc">${pair.n} 次</span>`;
    topBox.appendChild(row);
  });
  if (!s.cooccurrence.top.length) topBox.innerHTML = '<div class="empty">暂无数据</div>';
  grid.appendChild(topCard);
  body.appendChild(grid);

  const note = document.createElement("div");
  note.className = "card";
  note.style.marginTop = "12px";
  note.innerHTML = '<h3>怎么读</h3><div class="note">共现次数受号码自身频率影响，不能直接当作“组合更热”。如果要做关联规则，应同时看支持度、置信度与提升度，并用滚动窗口复核；单看热力图容易把随机波动误认为规律。</div>';
  body.appendChild(note);
}

function renderTest(body, s) {
  const cards = [];
  [{ key: "red", label: "红球", n: 33 }, { key: "blue", label: "蓝球", n: 16 }].forEach(({ key, label, n }) => {
    const data = s[key];
    const cardEl = card(`${label}均匀性检验`, `卡方拟合优度 · 期望 ${data.expected} 次/号`);
    const verdict = document.createElement("div");
    const ok = Number(data.p) > 0.05;
    verdict.className = `verdict ${ok ? "ok" : "warn"}`;
    verdict.textContent = ok ? "p > 0.05，不能拒绝均匀随机" : "p ≤ 0.05，存在统计偏离";
    cardEl.appendChild(verdict);
    const kv = document.createElement("div");
    kv.innerHTML = `
      <div class="kv"><span>样本期数</span><b>${s.n}</b></div>
      <div class="kv"><span>χ² 统计量</span><b>${data.chi2}</b></div>
      <div class="kv"><span>自由度 df</span><b>${data.df}</b></div>
      <div class="kv"><span>p 值</span><b>${fmtP(data.p)}</b></div>
      <div class="kv"><span>号码数</span><b>${n}</b></div>
    `;
    cardEl.appendChild(kv);
    cards.push(cardEl);
  });
  addCards(body, cards);

  const note = document.createElement("div");
  note.className = "card";
  note.style.marginTop = "12px";
  note.innerHTML = '<h3>p 值不是中奖概率</h3><div class="note">卡方检验回答的是“当前样本与均匀分布是否有显著差异”。p > 0.05 只表示没有足够证据证明存在偏向，不等于证明绝对公平；p ≤ 0.05 也可能是多重比较或小样本造成的假阳性。建议切换近 30 / 近 300 / 全量三个窗口交叉看，而不是用单一结果下结论。</div>';
  body.appendChild(note);
}

// ========== 回测 ==========
function renderBacktest() {
  const body = $("#statBody");
  body.innerHTML = "";
  const list = state.config?.strategies || defaultStrategies();
  const strategyOptions = list.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
  const formCard = card("策略回测", "walk-forward：每期只用当期之前的数据生成号码，再与当期开奖比对");
  const form = document.createElement("form");
  form.className = "backtest-form";
  form.innerHTML = `
    <label>策略<select id="btStrategy">${strategyOptions}</select></label>
    <label>统计窗口<select id="btWindow">
      <option value="30">近 30 期</option>
      <option value="100" selected>近 100 期</option>
      <option value="300">近 300 期</option>
      <option value="500">近 500 期</option>
    </select></label>
    <label>每期注数<input id="btTickets" type="number" min="1" max="20" value="5"></label>
    <label>起始序号<input id="btStart" type="number" min="30" max="${Math.max(30, (state.meta?.count || 60) - 1)}" value="300"></label>
    <button class="btn primary" type="submit">运行回测</button>
  `;
  formCard.appendChild(form);
  body.appendChild(formCard);

  const result = document.createElement("div");
  result.id = "btResult";
  result.style.marginTop = "12px";
  if (state.backtestResult) {
    renderBacktestResult(result, state.backtestResult);
  } else {
    result.innerHTML = '<div class="card"><div class="empty">选择策略与注数，运行一次回测；会同时跑同注数的纯随机基线。</div></div>';
  }
  body.appendChild(result);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const strategy = $("#btStrategy").value;
    const window = Number($("#btWindow").value);
    const ticketsPerDraw = Number($("#btTickets").value);
    const start = Number($("#btStart").value);
    const button = form.querySelector("button");
    button.disabled = true;
    button.classList.add("loading");
    result.innerHTML = '<div class="card"><div class="empty">回测运行中…（全量约 1–3 秒）</div></div>';
    try {
      const data = await api.backtest({
        strategy,
        params: { window },
        ticketsPerDraw,
        start,
        seed: 20261104,
      });
      state.backtestResult = data;
      renderBacktestResult(result, data);
      toast(`回测完成：${data.tickets} 注，耗时 ${data.elapsedMs}ms`, "ok");
    } catch (error) {
      result.innerHTML = "";
      const errorCard = card("回测失败");
      const p = document.createElement("div");
      p.className = "note";
      p.textContent = error.message;
      errorCard.appendChild(p);
      result.appendChild(errorCard);
      toast(`回测失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
      button.classList.remove("loading");
    }
  });
}

function renderBacktestResult(container, data) {
  container.innerHTML = "";
  const metrics = document.createElement("div");
  metrics.className = "result-metrics";
  const items = [
    ["总投入", money(data.cost), ""],
    ["总奖金", money(data.prize), "cyan"],
    ["回报率", pct(data.roi), "cyan"],
    ["随机基线", pct(data.baseline.roi), ""],
    ["差值", `${data.deltaRoi >= 0 ? "+" : ""}${pct(data.deltaRoi, 2)}`, data.deltaRoi >= 0 ? "good" : "bad"],
  ];
  items.forEach(([k, v, cls]) => {
    const metric = document.createElement("div");
    metric.className = "metric";
    metric.innerHTML = `<div class="k">${k}</div><div class="v ${cls}">${v}</div>`;
    metrics.appendChild(metric);
  });
  container.appendChild(metrics);

  const tableCard = card(
    "奖级分布",
    `${data.strategyName} · ${data.ticketsPerDraw} 注/期 · ${data.draws} 期 · ${data.startCode} ~ ${data.endCode}`,
  );
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "level-table";
  table.innerHTML = `<thead><tr><th>奖级</th><th>策略命中</th><th>随机命中</th><th>单注奖金</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  data.levels.forEach((level, index) => {
    const base = data.baseline.levels[index];
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${level.name}</td><td>${level.count}</td><td>${base.count}</td><td>${money(level.amount)}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  tableCard.appendChild(wrap);
  container.appendChild(tableCard);

  const note = document.createElement("div");
  note.className = "card";
  note.style.marginTop = "12px";
  note.innerHTML = `<h3>读结果前先看这三件事</h3><div class="note">
    1. 一等奖按 ${money(data.assumptions.firstPrize)}、二等奖按 ${money(data.assumptions.secondPrize)} 的均值假设；实际浮动奖金额会变。<br>
    2. 奖金方差极大，几万注里中一次头奖就会完全改变回报率；短期差值不代表策略优劣。<br>
    3. 随机基线使用同注数、同 seed 规则的纯随机号码；如果策略与基线差异在噪声范围内，说明历史规律没有转化为优势。
  </div>`;
  container.appendChild(note);
}

// ========== 智能生成 ==========
function readFilters() {
  const sumMin = Number($("#fSumMin").value);
  const sumMax = Number($("#fSumMax").value);
  const oddMin = Number($("#fOddMin").value);
  const oddMax = Number($("#fOddMax").value);
  const spanMin = Number($("#fSpanMin").value);
  const spanMax = Number($("#fSpanMax").value);
  const consecutiveMax = Number($("#fConsec").value || 5);
  if (![sumMin, sumMax, oddMin, oddMax, spanMin, spanMax, consecutiveMax].every(Number.isFinite)) {
    throw new Error("过滤参数必须是数字");
  }
  if (sumMin > sumMax) throw new Error("和值下限不能大于上限");
  if (oddMin > oddMax) throw new Error("奇数个数下限不能大于上限");
  if (spanMin > spanMax) throw new Error("跨度下限不能大于上限");
  const exclude = parseNumberList($("#fExclude").value).filter((n) => n >= 1 && n <= 33);
  return {
    sum_min: sumMin,
    sum_max: sumMax,
    odd_min: oddMin,
    odd_max: oddMax,
    span_min: spanMin,
    span_max: spanMax,
    consecutive_max: consecutiveMax,
    exclude,
  };
}

async function generateNumbers() {
  const button = $("#generateBtn");
  const strategy = $("#strategySel").value;
  const count = Math.max(1, Math.min(20, Number($("#genCount").value) || 5));
  const window = Number($("#strategyWindow").value);
  const useFilters = $("#useFilters").checked;
  let filters = {};
  if (useFilters) {
    try {
      filters = readFilters();
    } catch (error) {
      toast(error.message, "error");
      return;
    }
  }
  button.disabled = true;
  button.classList.add("loading");
  try {
    const data = await api.generate({ strategy, count, params: { window, filters } });
    state.lastGen = data.tickets;
    state.genStrategy = data.strategy;
    state.genStrategyName = data.strategyName;
    renderGenResult();
    toast(`已生成 ${data.count} 注`, "ok");
  } catch (error) {
    toast(`生成失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

function renderGenResult() {
  const box = $("#genResult");
  box.innerHTML = "";
  if (!state.lastGen.length) return;
  state.lastGen.forEach((ticket) => {
    const item = document.createElement("div");
    item.className = "gen-item";
    const nums = document.createElement("span");
    nums.className = "nums";
    nums.innerHTML = `<span class="r">${ticket.r.map(zero).join(" ")}</span><span class="b">${zero(ticket.b)}</span>`;
    const tags = document.createElement("span");
    tags.className = "tags";
    (ticket.tags || []).forEach((tag) => {
      const badge = document.createElement("span");
      badge.className = "tag";
      badge.textContent = tag;
      tags.appendChild(badge);
    });
    item.append(nums, tags);
    box.appendChild(item);
  });
  const actions = document.createElement("div");
  actions.className = "gen-actions";
  const save = document.createElement("button");
  save.type = "button";
  save.className = "btn primary small";
  save.textContent = `全部存入（${state.lastGen.length} 注）`;
  save.addEventListener("click", () => {
    addRecords(state.lastGen, state.genStrategy, state.genStrategyName, [state.genStrategyName]);
    toast(`已存入 ${state.lastGen.length} 注`, "ok");
    state.lastGen = [];
    renderGenResult();
  });
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "btn small ghost";
  clear.textContent = "清空结果";
  clear.addEventListener("click", () => {
    state.lastGen = [];
    renderGenResult();
  });
  actions.append(save, clear);
  box.appendChild(actions);
}

// ========== 旋转矩阵 ==========
function populateWheelBlue() {
  const select = $("#wheelBlue");
  if (!select) return;
  for (let n = 1; n <= 16; n += 1) {
    const option = document.createElement("option");
    option.value = String(n);
    option.textContent = zero(n);
    select.appendChild(option);
  }
}

function openWheel() {
  const dialog = $("#wheelDialog");
  const pool = state.red.size >= 7 && state.red.size <= 12
    ? [...state.red].sort((a, b) => a - b)
    : [1, 3, 5, 7, 9, 11, 13];
  $("#wheelPool").value = pool.join(",");
  $("#wheelResult").innerHTML = "";
  $("#wheelSave").disabled = true;
  state.wheelTickets = [];
  dialog.showModal();
}

async function runWheel() {
  const pool = [...new Set(parseNumberList($("#wheelPool").value))].filter((n) => n >= 1 && n <= 33).sort((a, b) => a - b);
  if (pool.length < 7 || pool.length > 12) {
    toast("号码池需要 7–12 个红球", "error");
    return;
  }
  const guarantee = Number($("#wheelGuarantee").value);
  const button = $("#wheelRun");
  button.disabled = true;
  button.classList.add("loading");
  try {
    const data = await api.wheel({ pool, guarantee });
    state.wheelTickets = data.tickets;
    const box = $("#wheelResult");
    box.innerHTML = "";
    const summary = document.createElement("div");
    summary.className = "summary-strip";
    summary.innerHTML = `<span>生成 <b>${data.ticketCount}</b> 注</span><span>覆盖 <b>${pct(data.coverage)}</b></span><span>池内组合 <b>${data.poolCombinations}</b></span><span>耗时 <b>${data.elapsedMs}ms</b></span>`;
    box.appendChild(summary);
    const preview = document.createElement("div");
    preview.className = "gen-result";
    data.tickets.slice(0, 12).forEach((reds) => {
      const item = document.createElement("div");
      item.className = "gen-item";
      item.innerHTML = `<span class="nums"><span class="r">${reds.map(zero).join(" ")}</span></span>`;
      preview.appendChild(item);
    });
    if (data.tickets.length > 12) {
      const more = document.createElement("div");
      more.className = "note";
      more.textContent = `另有 ${data.tickets.length - 12} 注…`;
      preview.appendChild(more);
    }
    box.appendChild(preview);
    $("#wheelSave").disabled = false;
    toast(`矩阵生成完成：${data.ticketCount} 注，覆盖 ${pct(data.coverage)}`, "ok");
  } catch (error) {
    toast(`矩阵生成失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

function saveWheel() {
  if (!state.wheelTickets.length) return;
  const blue = Number($("#wheelBlue").value);
  const guarantee = $("#wheelGuarantee").value;
  const tickets = state.wheelTickets.map((reds) => ({
    r: reds,
    b: blue,
    tags: [`旋转矩阵 中6保${guarantee}`, `蓝球${zero(blue)}`],
  }));
  if (tickets.length > MAX_RECORDS) {
    toast(`单次最多存 ${MAX_RECORDS} 注，当前 ${tickets.length} 注`, "error");
    return;
  }
  addRecords(tickets, "wheel", `旋转矩阵·保${guarantee}`, [`旋转矩阵 中6保${guarantee}`]);
  toast(`已存入 ${tickets.length} 注，${money(tickets.length * 2)}`, "ok");
  state.wheelTickets = [];
  $("#wheelDialog").close();
}

// ========== 事件绑定 ==========
function bindEvents() {
  $("#modeTabs").addEventListener("click", (event) => {
    const tab = event.target.closest(".tab");
    if (tab) switchMode(tab.dataset.mode);
  });

  $("#dantuoSwitch").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.editSet = button.dataset.set;
    renderSelection();
  });

  $("#saveBtn").addEventListener("click", saveSelection);
  $("#randomBtn").addEventListener("click", randomFill);
  $("#clearBtn").addEventListener("click", clearSelection);
  $("#wheelOpenBtn").addEventListener("click", openWheel);
  $("#syncBtn").addEventListener("click", syncData);
  $("#exportBtn").addEventListener("click", exportRecords);
  $("#clearRecBtn").addEventListener("click", clearRecords);

  $("#statTabs").addEventListener("click", (event) => {
    const tab = event.target.closest(".tab");
    if (!tab) return;
    state.statsTab = tab.dataset.tab;
    $$("#statTabs .tab").forEach((item) => item.classList.toggle("on", item === tab));
    $("#windowSwitch").style.display = state.statsTab === "backtest" ? "none" : "flex";
    renderStats();
  });

  $("#windowSwitch").addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (!chip) return;
    state.statsWindow = chip.dataset.window;
    $$("#windowSwitch .chip").forEach((item) => item.classList.toggle("on", item === chip));
    loadStats();
  });

  $("#strategySel").addEventListener("change", () => {
    const custom = $("#strategySel").value === "custom";
    $("#useFilters").checked = custom;
    $("#filterGrid").hidden = !custom;
  });
  $("#useFilters").addEventListener("change", () => {
    $("#filterGrid").hidden = !$("#useFilters").checked;
  });
  $("#generateBtn").addEventListener("click", generateNumbers);
  $("#genClearBtn").addEventListener("click", () => {
    state.lastGen = [];
    renderGenResult();
  });

  $("#wheelRun").addEventListener("click", runWheel);
  $("#wheelSave").addEventListener("click", saveWheel);
  $("#wheelClose").addEventListener("click", () => $("#wheelDialog").close());
  $("#wheelDialog").addEventListener("click", (event) => {
    if (event.target === $("#wheelDialog")) $("#wheelDialog").close();
  });
}