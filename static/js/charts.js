// 轻量图表：柱状、横条、折线、热力图，无第三方依赖
import { pct } from "./util.js";

export function barChart(container, items, options = {}) {
  const { color = "", showValue = items.length <= 20, height = 132 } = options;
  container.innerHTML = "";
  container.className = `bars ${color}`.trim();
  container.style.height = `${height}px`;
  const values = items.map((x) => Number(x.value) || 0);
  const max = Math.max(...values, 1);
  items.forEach((item, index) => {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.title = item.title || `${item.label}: ${item.value}`;
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.height = `${Math.max(2, (values[index] / max) * 100)}%`;
    if (item.color) fill.style.background = item.color;
    const value = document.createElement("div");
    value.className = "val";
    value.textContent = showValue ? item.value : "";
    const label = document.createElement("div");
    label.className = "lbl";
    label.textContent = item.label;
    bar.append(value, fill, label);
    container.appendChild(bar);
  });
}

export function hBars(container, items, options = {}) {
  const { color = "", total = 0, limit = 0, valueFormatter = null } = options;
  container.innerHTML = "";
  const list = limit > 0 ? items.slice(0, limit) : items;
  const max = Math.max(...list.map((x) => Number(x.n) || 0), 1);
  list.forEach((item) => {
    const row = document.createElement("div");
    row.className = `hline ${color}`.trim();
    const key = document.createElement("div");
    key.className = "k";
    key.textContent = item.key;
    key.title = item.key;
    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.width = `${Math.max(1, ((Number(item.n) || 0) / max) * 100)}%`;
    track.appendChild(fill);
    const value = document.createElement("div");
    value.className = "v";
    const n = Number(item.n) || 0;
    value.textContent = valueFormatter ? valueFormatter(n, item) : total ? `${n} · ${pct(n / total)}` : String(n);
    row.append(key, track, value);
    container.appendChild(row);
  });
  if (!list.length) {
    container.innerHTML = '<div class="empty">暂无数据</div>';
  }
}

let sparkId = 0;
export function sparkline(container, points, options = {}) {
  container.innerHTML = "";
  const values = points.map((p) => Number(p.v) || 0);
  if (!values.length) {
    container.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const width = 600;
  const height = 90;
  const pad = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  const coords = values.map((v, i) => {
    const x = pad + i * step;
    const y = height - pad - ((v - min) / span) * (height - pad * 2);
    return [x, y];
  });
  const line = coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${(pad + (values.length - 1) * step).toFixed(1)},${height - pad} L${pad},${height - pad} Z`;
  const id = `spark-${sparkId += 1}`;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "spark");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = `
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${options.color || "#22d3ee"}" stop-opacity=".55"/>
      <stop offset="100%" stop-color="${options.color || "#22d3ee"}" stop-opacity="0"/>
    </linearGradient></defs>
    <path class="area" d="${area}" fill="url(#${id})"/>
    <path class="line" d="${line}" stroke="${options.color || "#22d3ee"}"/>
  `;
  container.appendChild(svg);
  const labels = document.createElement("div");
  labels.className = "spark-labels";
  labels.innerHTML = `<span>${points[0].c} · ${values[0]}</span><span>${points[points.length - 1].c} · ${values[values.length - 1]}</span>`;
  container.appendChild(labels);
}

export function heatmap(container, matrix, options = {}) {
  container.innerHTML = "";
  const size = 33;
  const max = Number(options.max) || 1;
  const grid = document.createElement("div");
  grid.className = "heatmap";

  const corner = document.createElement("div");
  corner.className = "hm-label";
  grid.appendChild(corner);
  for (let col = 1; col <= size; col += 1) {
    const label = document.createElement("div");
    label.className = "hm-label";
    label.textContent = col;
    grid.appendChild(label);
  }
  for (let row = 1; row <= size; row += 1) {
    const rowLabel = document.createElement("div");
    rowLabel.className = "hm-label";
    rowLabel.textContent = row;
    grid.appendChild(rowLabel);
    for (let col = 1; col <= size; col += 1) {
      const value = Number(matrix?.[row]?.[col] || 0);
      const cell = document.createElement("div");
      cell.className = "hm-cell";
      if (row === col) {
        cell.style.background = "rgba(255,255,255,.025)";
      } else {
        const alpha = value > 0 ? 0.05 + 0.78 * (value / max) : 0.02;
        cell.style.background = `rgba(34,211,238,${alpha.toFixed(3)})`;
      }
      cell.title = `${String(row).padStart(2, "0")} + ${String(col).padStart(2, "0")}：${value} 次`;
      grid.appendChild(cell);
    }
  }
  container.appendChild(grid);

  const legend = document.createElement("div");
  legend.className = "heat-legend";
  legend.innerHTML = `<span>少</span><i style="background:rgba(34,211,238,.08)"></i><i style="background:rgba(34,211,238,.3)"></i><i style="background:rgba(34,211,238,.6)"></i><i style="background:rgba(34,211,238,.9)"></i><span>多（最大 ${max} 次）</span>`;
  container.appendChild(legend);
}