# mistick · 双色球选号台

一个本地运行的双色球选号与数据分析工具。后端 Python 标准库零依赖，前端原生 HTML/CSS/JS 零依赖，数据留在本机。

默认地址：**http://127.0.0.1:3100/**

> 开奖是独立随机事件。本项目的策略只改变号码分布、覆盖范围与投注成本，**不提高单注中奖概率**。请理性购彩，未成年人禁止购买彩票。

## 快速开始

```powershell
cd mistick
python run.py
```

浏览器打开 http://127.0.0.1:3100/。

指定端口：

```powershell
python run.py --port 3100 --host 127.0.0.1
```

同步开奖数据（也可以点页面上的「同步数据」）：

```powershell
python scripts/sync.py
```

运行测试：

```powershell
python -m unittest discover -s tests -v
python scripts/verify.py
```

## 项目结构

```text
mistick/
├─ app/                 后端
│  ├─ config.py         配置加载（config.json / 环境变量 / 命令行）
│  ├─ store.py          开奖库读写、原子替换、按期号合并
│  ├─ upstream.py       福彩官方 + 500 网双源同步
│  ├─ analytics.py      频次、遗漏、和值、形态、共现、卡方检验
│  ├─ strategies.py     策略引擎（权重采样 + 硬过滤）
│  ├─ backtest.py       walk-forward 回测与随机基线
│  ├─ wheel.py          旋转矩阵覆盖设计
│  ├─ api.py            业务 API 与参数校验
│  └─ server.py         HTTP 服务、静态托管、日志
├─ static/              前端
│  ├─ index.html
│  ├─ css/app.css
│  └─ js/{api,app,charts,util}.js
├─ data/draws.json      开奖库（唯一数据源）
├─ draws.json           旧 8761 代理数据库（legacy，可删）
├─ tests/               unittest 测试
├─ scripts/             sync.py / verify.py
├─ config.json          默认配置（端口 3100）
├─ run.py               启动入口
└─ legacy/              旧版单文件页面与 Ruby 代理（仅归档）
```

## 功能

### 选号

- **单式**：6 红 + 1 蓝。
- **复式**：红球 7–20 个，蓝球 1–16 个，实时计算注数与金额。
- **胆拖**：胆码 1–5 个，拖码补足 6 个，红球合计 ≤20。
- **智能生成**：纯随机、热号跟随、冷号回补、遗漏回补、均衡形态、避开热门、自定义过滤。
- **旋转矩阵**：7–12 个红球做覆盖设计，支持“中 6 保 5 / 中 6 保 6”，生成后自校验覆盖率。
- 注单保存在浏览器 localStorage，支持导出 JSON、按最新开奖自动判奖。

### 统计

- 红/蓝频次与卡方拟合优度检验（p 值）。
- 遗漏：当前、平均、最大遗漏。
- 和值：分布、均值、标准差、最近 30 期走势。
- 形态：跨度、AC 值、质合比、012 路、尾数、同尾、连号、重号、邻号。
- 关系：33×33 号码共现热力图、高频号码对。
- 回测：walk-forward 策略回测，同注数纯随机基线对照，奖级分布、投入、奖金、回报率。
- 统计窗口：全量 / 近 300 / 近 30。

### 数据

- 2013 年及以后来自福彩官方接口。
- 2003–2012 来自 500 网历史页。
- 同步时按期号合并，官方数据优先；写入采用临时文件 + `os.replace` 原子替换。
- 当前库约 3500 期，文件约 330 KB。

## 配置

`config.json`：

```json
{
  "host": "127.0.0.1",
  "port": 3100,
  "data_file": "data/draws.json",
  "static_dir": "static",
  "log_dir": "logs",
  "auto_sync": false,
  "sync_interval_hours": 24,
  "request_timeout": 30,
  "first_prize": 7000000,
  "second_prize": 200000,
  "max_body_bytes": 1048576
}
```

优先级：命令行 > 环境变量（`MISTICK_PORT` 等）> `config.json` > 默认值。

- `auto_sync`：开启后台定时同步。
- `first_prize` / `second_prize`：回测中一、二等奖的均值假设，仅用于估算。
- 默认只监听 `127.0.0.1`，不对外网开放。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查、版本、期数 |
| GET | `/api/meta` | 库首尾期号、总期数 |
| GET | `/api/config` | 策略列表、限制、奖金假设 |
| GET | `/api/draws?limit=30&offset=0&order=desc` | 分页开奖 |
| GET | `/api/stats?window=all\|300\|30` | 全量统计 |
| POST | `/api/generate` | 生成注单 |
| POST | `/api/backtest` | 回测 |
| POST | `/api/wheel` | 旋转矩阵 |
| POST | `/api/sync` | 双源同步 |

生成示例：

```json
{
  "strategy": "balanced",
  "count": 5,
  "params": {
    "window": 100,
    "filters": { "sum_min": 80, "sum_max": 130 }
  }
}
```

回测示例：

```json
{
  "strategy": "hot",
  "params": { "window": 100 },
  "ticketsPerDraw": 5,
  "start": 300,
  "seed": 20261104
}
```

## 实现说明

### 策略管线

```text
候选池 → 硬过滤（和值/奇偶/跨度/连号/重号/AC/质合/三区/排除）→ 加权无放回抽样 → 去重 → 注单
```

加权抽样使用 Efraimidis–Spirakis：为每个号码生成 `random^(1/weight)`，取最大的 6 个。热号、冷号、遗漏、避热门只改变权重；均衡形态主要靠硬过滤。

### 回测

从 `start` 期开始逐期推进，每期只用之前的数据生成号码，再与当期开奖比对。策略与同注数纯随机基线同时运行。一、二等奖按配置均值估算，三至六等奖按固定奖金。

历史回测中，任何策略与随机基线的差异都应落在噪声范围内；如果某种策略看起来长期稳定跑赢，优先怀疑过拟合或数据泄漏。

### 旋转矩阵

在号码池内枚举所有 6 码组合，用贪心集合覆盖选择注单，生成后枚举校验覆盖率。它只保证“开奖号全在池内时至少中 guarantee 个”，不改变期望收益。

## 测试

- 40 个 unittest：数据规范化、原子写入、频次/遗漏/卡方、策略过滤、奖级边界、回测成本、旋转矩阵、API 路由。
- `scripts/verify.py` 额外检查开奖库完整性（每期 6 个 1–33 的不重复红球、1–16 的蓝球）。

## 旧版

`legacy/` 保留了改造前的 `ssq.html` 和 `proxy.rb`，仅作参考。项目根目录的 `draws.json` 是旧 8761 代理使用的 3521 期旧库；新服务唯一数据源是 `data/draws.json`。停用旧代理后可以删除根目录的旧库。
