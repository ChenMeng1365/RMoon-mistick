# coding: utf-8
"""旋转矩阵：在号码池内做覆盖设计，保证开奖号全在池内时至少中 guarantee 个。"""

from __future__ import annotations

import time
from functools import lru_cache
from itertools import combinations
from typing import Any

from .strategies import StrategyError


@lru_cache(maxsize=64)
def _build(pool: tuple[int, ...], guarantee: int) -> tuple[tuple[int, ...], ...]:
    n = len(pool)
    all_sets = list(combinations(range(n), 6))
    if guarantee == 6:
        return tuple(tuple(pool[i] for i in combo) for combo in all_sets)

    set_masks = [sum(1 << i for i in combo) for combo in all_sets]
    coverage: list[int] = []
    for ticket in all_sets:
        tmask = sum(1 << i for i in ticket)
        mask = 0
        for idx, wmask in enumerate(set_masks):
            if (tmask & wmask).bit_count() >= guarantee:
                mask |= 1 << idx
        coverage.append(mask)

    full = (1 << len(all_sets)) - 1
    uncovered = full
    chosen: list[tuple[int, ...]] = []
    while uncovered:
        best = -1
        best_gain = 0
        for idx, mask in enumerate(coverage):
            gain = (mask & uncovered).bit_count()
            if gain > best_gain:
                best_gain = gain
                best = idx
        if best < 0 or best_gain == 0:
            raise StrategyError("覆盖设计失败，请减少号码池")
        chosen.append(tuple(pool[i] for i in all_sets[best]))
        uncovered &= ~coverage[best]
    return tuple(chosen)


def build_wheel(pool: list[int], guarantee: int = 5) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        clean = sorted({int(x) for x in pool})
    except (TypeError, ValueError) as exc:
        raise StrategyError("号码池必须是 1-33 的整数") from exc
    if not 7 <= len(clean) <= 12:
        raise StrategyError("旋转矩阵号码池建议 7-12 个红球")
    if any(x < 1 or x > 33 for x in clean):
        raise StrategyError("号码池必须在 1-33 之间")
    if guarantee not in (5, 6):
        raise StrategyError("guarantee 只支持 5 或 6")

    tickets = _build(tuple(clean), guarantee)
    total = 1
    for i in range(6):
        total = total * (len(clean) - 6 + i + 1) // (i + 1)
    # 覆盖校验：枚举池内所有 6 码组合，确认至少一注命中 guarantee 个
    covered = 0
    for target in combinations(clean, 6):
        target_set = set(target)
        if any(len(target_set & set(ticket)) >= guarantee for ticket in tickets):
            covered += 1

    return {
        "pool": clean,
        "guarantee": guarantee,
        "tickets": [list(t) for t in tickets],
        "ticketCount": len(tickets),
        "poolCombinations": total,
        "coverage": round(covered / total, 4) if total else 0.0,
        "elapsedMs": int((time.perf_counter() - started) * 1000),
    }