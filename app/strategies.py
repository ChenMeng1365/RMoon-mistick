# coding: utf-8
"""选号策略引擎：权重采样 + 硬过滤 + 去重。"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from .analytics import PRIMES, parse_blue, parse_reds

STRATEGIES = {
    "random": "纯随机",
    "hot": "热号跟随",
    "cold": "冷号回补",
    "omission": "遗漏回补",
    "balanced": "均衡形态",
    "avoid": "避开热门",
    "custom": "自定义过滤",
}

DEFAULT_FILTERS: dict[str, Any] = {
    "odd_min": 0,
    "odd_max": 6,
    "big_min": 0,
    "big_max": 6,
    "sum_min": 21,
    "sum_max": 183,
    "span_min": 5,
    "span_max": 32,
    "consecutive_max": 5,
    "repeat_max": 6,
    "ac_min": 0,
    "ac_max": 10,
    "prime_min": 0,
    "prime_max": 6,
    "zone_min": [0, 0, 0],
    "zone_max": [6, 6, 6],
    "include": [],
    "exclude": [],
}

BALANCED_PRESET: dict[str, Any] = {
    "odd_min": 2,
    "odd_max": 4,
    "big_min": 2,
    "big_max": 4,
    "sum_min": 80,
    "sum_max": 130,
    "span_min": 18,
    "span_max": 32,
    "consecutive_max": 1,
    "repeat_max": 2,
    "ac_min": 5,
    "ac_max": 10,
    "prime_min": 1,
    "prime_max": 4,
    "zone_min": [1, 1, 1],
}


class StrategyError(Exception):
    """策略参数不合法，或过滤条件过严生成不出注单。"""


def _int(value: Any, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise StrategyError(f"{name} 必须是整数") from exc
    if not low <= number <= high:
        raise StrategyError(f"{name} 必须在 {low}-{high} 之间")
    return number


def _int_list(value: Any, name: str, max_len: int | None = None) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise StrategyError(f"{name} 必须是数组")
    out: list[int] = []
    for item in value:
        number = _int(item, name, 1, 33)
        if number not in out:
            out.append(number)
    if max_len is not None and len(out) > max_len:
        raise StrategyError(f"{name} 最多 {max_len} 个")
    return sorted(out)


def normalize_filters(filters: dict[str, Any] | None, strategy: str) -> dict[str, Any]:
    base = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_FILTERS.items()}
    if strategy == "balanced":
        for key, value in BALANCED_PRESET.items():
            base[key] = list(value) if isinstance(value, list) else value
    if filters:
        if not isinstance(filters, dict):
            raise StrategyError("filters 必须是对象")
        for key, value in filters.items():
            if key in base:
                base[key] = value

    result: dict[str, Any] = {}
    for prefix, low, high in (
        ("odd", 0, 6),
        ("big", 0, 6),
        ("sum", 21, 183),
        ("span", 5, 32),
        ("ac", 0, 10),
        ("prime", 0, 6),
    ):
        result[f"{prefix}_min"] = _int(base.get(f"{prefix}_min"), f"{prefix}_min", low, high)
        result[f"{prefix}_max"] = _int(base.get(f"{prefix}_max"), f"{prefix}_max", low, high)
        if result[f"{prefix}_min"] > result[f"{prefix}_max"]:
            raise StrategyError(f"{prefix}_min 不能大于 {prefix}_max")
    result["consecutive_max"] = _int(base.get("consecutive_max"), "consecutive_max", 0, 5)
    result["repeat_max"] = _int(base.get("repeat_max"), "repeat_max", 0, 6)

    zone_min = base.get("zone_min") or [0, 0, 0]
    zone_max = base.get("zone_max") or [6, 6, 6]
    if not isinstance(zone_min, (list, tuple)) or len(zone_min) != 3:
        raise StrategyError("zone_min 必须是长度 3 的数组")
    if not isinstance(zone_max, (list, tuple)) or len(zone_max) != 3:
        raise StrategyError("zone_max 必须是长度 3 的数组")
    result["zone_min"] = [_int(x, "zone_min", 0, 6) for x in zone_min]
    result["zone_max"] = [_int(x, "zone_max", 0, 6) for x in zone_max]
    for i in range(3):
        if result["zone_min"][i] > result["zone_max"][i]:
            raise StrategyError(f"第 {i + 1} 区 zone_min 不能大于 zone_max")

    result["include"] = _int_list(base.get("include"), "include", 6)
    result["exclude"] = _int_list(base.get("exclude"), "exclude")
    if set(result["include"]) & set(result["exclude"]):
        raise StrategyError("include 与 exclude 不能有交集")
    return result


def _ac(reds: list[int]) -> int:
    diffs = {b - a for i, a in enumerate(reds) for b in reds[i + 1:]}
    return len(diffs) - 5


def _zones(reds: list[int]) -> tuple[int, int, int]:
    return (
        sum(1 for x in reds if x <= 11),
        sum(1 for x in reds if 12 <= x <= 22),
        sum(1 for x in reds if x >= 23),
    )


class StrategyEngine:
    """滚动状态引擎。

    - 最近 window 期用于冷热权重。
    - 全量历史用于遗漏、上期重号/邻号。
    - advance() 逐期推进，回测时无需重复扫描历史。
    """

    def __init__(self, history: list[dict[str, Any]], window: int = 100,
                 filters: dict[str, Any] | None = None, strategy: str = "random"):
        self.strategy = strategy
        self.window = max(1, min(int(window), 500))
        self.filters = normalize_filters(filters, strategy)
        self._recent: deque[dict[str, Any]] = deque(maxlen=self.window)
        self.red_counts = [0] * 34
        self.blue_counts = [0] * 17
        self.red_hits = [0] * 34
        self.blue_hits = [0] * 17
        self.red_miss = [0] * 34
        self.blue_miss = [0] * 17
        self.last_red: set[int] = set()
        self.total = 0
        self.history: list[dict[str, Any]] = []
        for draw in history:
            self.advance(draw)

    def advance(self, draw: dict[str, Any]) -> None:
        reds = parse_reds(draw)
        blue = parse_blue(draw)

        if len(self._recent) == self.window:
            old = self._recent[0]
            for num in parse_reds(old):
                self.red_counts[num] -= 1
            self.blue_counts[parse_blue(old)] -= 1

        self._recent.append(draw)
        self.history.append(draw)
        for num in reds:
            self.red_counts[num] += 1
            self.red_hits[num] += 1
        self.blue_counts[blue] += 1
        self.blue_hits[blue] += 1

        for num in range(1, 34):
            self.red_miss[num] = 0 if num in reds else self.red_miss[num] + 1
        for num in range(1, 17):
            self.blue_miss[num] = 0 if num == blue else self.blue_miss[num] + 1

        self.last_red = set(reds)
        self.total += 1

    def _avg_miss(self, num: int) -> float:
        hits = self.red_hits[num]
        return (self.total - hits) / hits if hits else float(max(1, self.total))

    def _red_weights(self, strategy: str) -> list[float]:
        if strategy in ("random", "balanced", "custom"):
            return [1.0] * 34
        if strategy == "hot":
            expected = max(1e-9, len(self._recent) * 6 / 33)
            return [1.0] + [(self.red_counts[n] + 1) / (expected + 1) for n in range(1, 34)]
        if strategy == "cold":
            top = max(self.red_counts[1:], default=0)
            return [1.0] + [float(top - self.red_counts[n] + 1) for n in range(1, 34)]
        if strategy == "omission":
            return [1.0] + [
                (self.red_miss[n] + 1) / (self._avg_miss(n) + 1) for n in range(1, 34)
            ]
        if strategy == "avoid":
            weights = [1.0] * 34
            for n in range(1, 34):
                weight = 1.0
                if n <= 31:          # 日期号扎堆区
                    weight *= 0.45
                if n in self.last_red:
                    weight *= 0.55
                if (n - 1) in self.last_red or (n + 1) in self.last_red:
                    weight *= 0.8
                weights[n] = weight
            return weights
        raise StrategyError(f"未知策略: {strategy}")

    def _blue_weights(self, strategy: str) -> list[float]:
        if strategy in ("random", "balanced", "custom"):
            return [1.0] * 17
        if strategy == "hot":
            return [1.0] + [float(self.blue_counts[n] + 1) for n in range(1, 17)]
        if strategy == "cold":
            top = max(self.blue_counts[1:], default=0)
            return [1.0] + [float(top - self.blue_counts[n] + 1) for n in range(1, 17)]
        if strategy == "omission":
            return [1.0] + [float(self.blue_miss[n] + 1) for n in range(1, 17)]
        if strategy == "avoid":
            return [1.0] + [0.6 if n <= 12 else 1.0 for n in range(1, 17)]
        raise StrategyError(f"未知策略: {strategy}")

    @staticmethod
    def _sample(weights: list[float], k: int, rng: random.Random,
                pool: list[int] | None = None) -> list[int]:
        keyed = []
        numbers = pool if pool is not None else range(1, len(weights))
        for num in numbers:
            weight = max(weights[num], 1e-9)
            keyed.append((rng.random() ** (1.0 / weight), num))
        keyed.sort(reverse=True)
        return sorted(num for _, num in keyed[:k])

    def _passes(self, reds: list[int]) -> bool:
        f = self.filters
        odd = sum(1 for x in reds if x % 2)
        big = sum(1 for x in reds if x >= 17)
        total = sum(reds)
        span = max(reds) - min(reds)
        consecutive = sum(1 for a, b in zip(reds, reds[1:]) if b - a == 1)
        ac = _ac(reds)
        prime = sum(1 for x in reds if x in PRIMES)
        zones = _zones(reds)
        repeat = len(set(reds) & self.last_red) if self.last_red else 0

        if not f["odd_min"] <= odd <= f["odd_max"]:
            return False
        if not f["big_min"] <= big <= f["big_max"]:
            return False
        if not f["sum_min"] <= total <= f["sum_max"]:
            return False
        if not f["span_min"] <= span <= f["span_max"]:
            return False
        if consecutive > f["consecutive_max"]:
            return False
        if repeat > f["repeat_max"]:
            return False
        if not f["ac_min"] <= ac <= f["ac_max"]:
            return False
        if not f["prime_min"] <= prime <= f["prime_max"]:
            return False
        for i in range(3):
            if not f["zone_min"][i] <= zones[i] <= f["zone_max"][i]:
                return False
        if f["include"] and not set(f["include"]).issubset(reds):
            return False
        if f["exclude"] and set(f["exclude"]) & set(reds):
            return False
        return True

    def _sample_reds(self, weights: list[float], rng: random.Random) -> list[int]:
        include = list(self.filters["include"])
        exclude = set(self.filters["exclude"])
        base = sorted(include)
        need = 6 - len(base)
        pool = [
            n for n in range(1, 34)
            if n not in exclude and n not in set(base)
        ]
        if len(pool) < need:
            raise StrategyError("排除号码过多，剩余红球不足以组成一注")
        if need <= 0:
            return base
        return sorted(base + self._sample(weights, need, rng, pool))

    def _ticket(self, reds: list[int], blue: int, strategy: str) -> dict[str, Any]:
        odd = sum(1 for x in reds if x % 2)
        zones = _zones(reds)
        tags = [
            STRATEGIES[strategy],
            f"和值{sum(reds)}",
            f"奇偶{odd}:{6 - odd}",
            f"三区{zones[0]}:{zones[1]}:{zones[2]}",
        ]
        return {"r": reds, "b": blue, "tags": tags[:4]}

    def generate(self, count: int, rng: random.Random | None = None,
                 strategy: str | None = None) -> list[dict[str, Any]]:
        strategy = strategy or self.strategy
        if strategy not in STRATEGIES:
            raise StrategyError(f"未知策略: {strategy}")
        count = max(1, min(int(count), 100))
        rng = rng or random.Random()

        red_weights = self._red_weights(strategy)
        blue_weights = self._blue_weights(strategy)
        tickets: list[dict[str, Any]] = []
        seen: set[tuple[tuple[int, ...], int]] = set()
        attempts = 0
        max_attempts = max(4000, count * 1200)
        while len(tickets) < count and attempts < max_attempts:
            attempts += 1
            reds = self._sample_reds(red_weights, rng)
            if not self._passes(reds):
                continue
            blue = self._sample(blue_weights, 1, rng)[0]
            key = (tuple(reds), blue)
            if key in seen:
                continue
            seen.add(key)
            tickets.append(self._ticket(reds, blue, strategy))
        if not tickets:
            raise StrategyError("过滤条件过严，未生成任何注单；请放宽参数")
        if len(tickets) < count:
            raise StrategyError(
                f"过滤条件过严，只生成 {len(tickets)}/{count} 注；请放宽参数或减少注数"
            )
        return tickets