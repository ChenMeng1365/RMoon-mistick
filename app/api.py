# coding: utf-8
"""业务 API：参数校验、调用分析/策略/回测模块。"""

from __future__ import annotations

import threading
import time
from typing import Any

from . import __version__
from .analytics import build_stats
from .backtest import run_backtest
from .config import Config
from .store import DrawStore
from .strategies import STRATEGIES, StrategyError
from .upstream import Upstream, UpstreamError
from .wheel import build_wheel


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _body_dict(body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ApiError(400, "请求体必须是 JSON 对象")
    return body


def _int_param(value: Any, name: str, default: int, low: int, high: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{name} 必须是整数") from exc
    if not low <= number <= high:
        raise ApiError(400, f"{name} 必须在 {low}-{high} 之间")
    return number


def _strategy(value: Any) -> str:
    name = str(value or "random")
    if name not in STRATEGIES:
        raise ApiError(400, f"未知策略: {name}")
    return name


class App:
    def __init__(self, config: Config):
        self.config = config
        self.store = DrawStore(config.data_path)
        self.upstream = Upstream(config.request_timeout)
        self.version = __version__
        self.started = time.time()
        self.sync_lock = threading.Lock()
        self._stats_cache: dict[tuple, dict[str, Any]] = {}
        self._stats_lock = threading.Lock()
        self._auto_stop = threading.Event()

    # ---------- 通用 ----------
    def health(self) -> dict[str, Any]:
        try:
            count = self.store.count()
        except Exception:
            count = 0
        return {
            "ok": True,
            "service": "mistick",
            "version": self.version,
            "uptime": round(time.time() - self.started, 1),
            "draws": count,
        }

    def meta(self) -> dict[str, Any]:
        payload = self.store.meta()
        payload["version"] = self.version
        return payload

    def config_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "host": self.config.host,
            "port": self.config.port,
            "strategies": [{"id": key, "name": name} for key, name in STRATEGIES.items()],
            "windows": ["all", "300", "30"],
            "limits": {
                "maxGenerate": 100,
                "maxTicketsPerDraw": 20,
                "maxSavedTickets": 500,
                "maxWheelPool": 12,
            },
            "prizes": {
                "first": self.config.first_prize,
                "second": self.config.second_prize,
                "fixed": {"3": 3000, "4": 200, "5": 10, "6": 5},
            },
            "disclaimer": "开奖是独立随机事件；策略只改变覆盖、成本与号码分布，不提高单注中奖概率。",
        }

    # ---------- 开奖 ----------
    def draws(self, query: dict[str, list[str]]) -> dict[str, Any]:
        def one(key: str, default: str) -> str:
            values = query.get(key)
            return values[0] if values else default

        limit = _int_param(one("limit", "30"), "limit", 30, 1, 5000)
        offset = _int_param(one("offset", "0"), "offset", 0, 0, 1_000_000)
        order = one("order", "desc")
        if order not in ("desc", "asc"):
            raise ApiError(400, "order 只支持 desc/asc")
        return self.store.recent(limit=limit, offset=offset, order=order)

    def stats(self, query: dict[str, list[str]]) -> dict[str, Any]:
        values = query.get("window")
        window = values[0] if values else "all"
        if window not in ("all", "300", "30", "100"):
            window = str(_int_param(window, "window", 300, 1, 5000))
        meta = self.store.meta()
        key = (window, meta.get("updated_at"), meta.get("count"))
        with self._stats_lock:
            cached = self._stats_cache.get(key)
            if cached is not None:
                return cached
        payload = build_stats(self.store.all(), window)
        with self._stats_lock:
            self._stats_cache = {key: payload}
        return payload

    def sync(self) -> dict[str, Any]:
        if not self.sync_lock.acquire(blocking=False):
            raise ApiError(409, "同步正在进行，请稍后再试")
        try:
            result = self.upstream.sync(self.store)
            with self._stats_lock:
                self._stats_cache.clear()
            return result
        except UpstreamError as exc:
            raise ApiError(502, str(exc)) from exc
        finally:
            self.sync_lock.release()

    # ---------- 策略 ----------
    def generate(self, body: Any) -> dict[str, Any]:
        data = _body_dict(body)
        strategy = _strategy(data.get("strategy"))
        count = _int_param(data.get("count"), "count", 1, 1, 100)
        params = data.get("params") or {}
        if not isinstance(params, dict):
            raise ApiError(400, "params 必须是对象")
        window = _int_param(params.get("window"), "window", 100, 5, 500)
        seed = params.get("seed")
        if seed is not None:
            seed = _int_param(seed, "seed", 0, -2_147_483_648, 2_147_483_647)
        filters = params.get("filters")
        if filters is not None and not isinstance(filters, dict):
            raise ApiError(400, "filters 必须是对象")

        from .strategies import StrategyEngine
        engine = StrategyEngine(self.store.all(), window=window, filters=filters, strategy=strategy)
        import random as _random
        rng = _random.Random(seed) if seed is not None else _random.Random()
        try:
            tickets = engine.generate(count, rng)
        except StrategyError as exc:
            raise ApiError(400, str(exc)) from exc
        return {
            "strategy": strategy,
            "strategyName": STRATEGIES[strategy],
            "count": len(tickets),
            "tickets": tickets,
            "window": window,
            "note": "号码由权重采样与硬过滤生成；请理性购彩。",
        }

    def backtest(self, body: Any) -> dict[str, Any]:
        data = _body_dict(body)
        strategy = _strategy(data.get("strategy"))
        params = data.get("params") or {}
        if not isinstance(params, dict):
            raise ApiError(400, "params 必须是对象")
        window = _int_param(params.get("window"), "window", 100, 5, 500)
        filters = params.get("filters")
        if filters is not None and not isinstance(filters, dict):
            raise ApiError(400, "filters 必须是对象")
        tickets_per_draw = _int_param(data.get("ticketsPerDraw"), "ticketsPerDraw", 5, 1, 20)
        total = self.store.count()
        if total < 60:
            raise ApiError(400, "开奖库太短，至少需要 60 期才能回测")
        start = _int_param(data.get("start"), "start", min(300, total - 1), 30, total - 1)
        seed = data.get("seed")
        if seed is not None:
            seed = _int_param(seed, "seed", 0, -2_147_483_648, 2_147_483_647)
        try:
            return run_backtest(
                self.store.all(),
                strategy=strategy,
                params={"window": window, "filters": filters},
                tickets_per_draw=tickets_per_draw,
                start=start,
                seed=seed,
                first_prize=self.config.first_prize,
                second_prize=self.config.second_prize,
            )
        except StrategyError as exc:
            raise ApiError(400, str(exc)) from exc

    def wheel(self, body: Any) -> dict[str, Any]:
        data = _body_dict(body)
        pool = data.get("pool")
        if not isinstance(pool, list):
            raise ApiError(400, "pool 必须是数组")
        guarantee = _int_param(data.get("guarantee"), "guarantee", 5, 5, 6)
        try:
            return build_wheel(pool, guarantee)
        except StrategyError as exc:
            raise ApiError(400, str(exc)) from exc