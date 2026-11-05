# coding: utf-8
"""walk-forward 回测：策略 vs 同注数纯随机基线。"""

from __future__ import annotations

import random
import time
from typing import Any

from .analytics import parse_blue, parse_reds
from .strategies import STRATEGIES, StrategyEngine, StrategyError

FIXED_PRIZES = {3: 3000, 4: 200, 5: 10, 6: 5}
LEVEL_NAMES = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "四等奖", 5: "五等奖", 6: "六等奖"}


def prize_level(reds: list[int], blue: int, actual: dict[str, Any]) -> int:
    """按双色球奖级返回 0-6，0 表示未中奖。"""
    match_red = len(set(reds) & set(parse_reds(actual)))
    match_blue = int(blue) == parse_blue(actual)
    if match_red == 6 and match_blue:
        return 1
    if match_red == 6:
        return 2
    if match_red == 5 and match_blue:
        return 3
    if match_red == 5 or (match_red == 4 and match_blue):
        return 4
    if match_red == 4 or (match_red == 3 and match_blue):
        return 5
    if match_blue and match_red <= 2:
        return 6
    return 0


def _empty_levels() -> dict[int, int]:
    return {level: 0 for level in range(0, 7)}


def _levels_payload(counts: dict[int, int], prizes: dict[int, int]) -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 7):
        amount = int(prizes[level])
        rows.append(
            {
                "level": level,
                "name": LEVEL_NAMES[level],
                "count": int(counts.get(level, 0)),
                "amount": amount,
                "total": int(counts.get(level, 0)) * amount,
            }
        )
    return rows


def _prize_sum(counts: dict[int, int], prizes: dict[int, int]) -> int:
    return sum(int(counts.get(level, 0)) * int(prizes[level]) for level in range(1, 7))


def run_backtest(
    draws: list[dict[str, Any]],
    strategy: str = "random",
    params: dict[str, Any] | None = None,
    tickets_per_draw: int = 5,
    start: int = 300,
    seed: int | None = None,
    first_prize: int = 7_000_000,
    second_prize: int = 200_000,
) -> dict[str, Any]:
    started = time.perf_counter()
    if strategy not in STRATEGIES:
        raise StrategyError(f"未知策略: {strategy}")
    n = len(draws)
    if n < 60:
        raise StrategyError("开奖库太短，至少需要 60 期才能回测")
    tickets_per_draw = max(1, min(int(tickets_per_draw), 20))
    start = max(30, min(int(start), n - 1))
    params = params or {}
    window = max(5, min(int(params.get("window", 100)), 500))
    filters = params.get("filters")

    prizes = {1: int(first_prize), 2: int(second_prize), **FIXED_PRIZES}
    rng = random.Random(seed) if seed is not None else random.Random()
    baseline_rng = random.Random((seed + 7919) if seed is not None else None)

    engine = StrategyEngine(draws[:start], window, filters, strategy)
    baseline = StrategyEngine(draws[:start], window, None, "random")

    counts = _empty_levels()
    baseline_counts = _empty_levels()
    draws_used = 0
    for i in range(start, n):
        actual = draws[i]
        try:
            tickets = engine.generate(tickets_per_draw, rng)
        except StrategyError as exc:
            raise StrategyError(f"第 {actual['c']} 期生成失败: {exc}") from exc
        base_tickets = baseline.generate(tickets_per_draw, baseline_rng, "random")

        for ticket in tickets:
            counts[prize_level(ticket["r"], ticket["b"], actual)] += 1
        for ticket in base_tickets:
            baseline_counts[prize_level(ticket["r"], ticket["b"], actual)] += 1

        engine.advance(actual)
        baseline.advance(actual)
        draws_used += 1

    ticket_count = draws_used * tickets_per_draw
    cost = ticket_count * 2
    prize = _prize_sum(counts, prizes)
    base_prize = _prize_sum(baseline_counts, prizes)
    elapsed = int((time.perf_counter() - started) * 1000)

    return {
        "strategy": strategy,
        "strategyName": STRATEGIES[strategy],
        "ticketsPerDraw": tickets_per_draw,
        "start": start,
        "startCode": draws[start]["c"],
        "endCode": draws[-1]["c"],
        "draws": draws_used,
        "tickets": ticket_count,
        "cost": cost,
        "prize": prize,
        "roi": round(prize / cost, 4) if cost else 0.0,
        "levels": _levels_payload(counts, prizes),
        "baseline": {
            "prize": base_prize,
            "roi": round(base_prize / cost, 4) if cost else 0.0,
            "levels": _levels_payload(baseline_counts, prizes),
        },
        "deltaRoi": round((prize - base_prize) / cost, 4) if cost else 0.0,
        "assumptions": {"firstPrize": prizes[1], "secondPrize": prizes[2]},
        "elapsedMs": elapsed,
    }