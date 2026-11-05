# coding: utf-8
"""双色球统计分析。所有函数只读，返回可直接 JSON 化的结构。"""

from __future__ import annotations

import math
from collections import Counter
from statistics import mean, pstdev
from typing import Any, Callable, Iterable

RED_MAX = 33
BLUE_MAX = 16
PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}

SUM_BUCKETS = [(21, 70), (71, 90), (91, 110), (111, 130), (131, 160), (161, 183)]
SPAN_BUCKETS = [(0, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 32)]


def parse_reds(draw: dict[str, Any]) -> list[int]:
    return [int(x) for x in str(draw["r"]).split(",") if x]


def parse_blue(draw: dict[str, Any]) -> int:
    return int(draw["b"])


def window_slice(draws: list[dict[str, Any]], window: str | int) -> list[dict[str, Any]]:
    if window in (None, "", "all", "ALL", 0, "0"):
        return draws
    n = int(window)
    if n <= 0:
        return draws
    return draws[-n:]


# ---------- 卡方检验 ----------
def _gser(a: float, x: float) -> float:
    itmax, eps = 300, 3e-12
    ap = a
    summ = 1.0 / a
    delta = summ
    for _ in range(itmax):
        ap += 1.0
        delta *= x / ap
        summ += delta
        if abs(delta) < abs(summ) * eps:
            break
    return summ * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    itmax, eps, fpmin = 300, 3e-12, 1e-300
    b = x + 1.0 - a
    c = 1.0 / fpmin
    d = 1.0 / b
    h = d
    for i in range(1, itmax + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < fpmin:
            d = fpmin
        c = b + an / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(chi2: float, df: int) -> float:
    """卡方分布上尾概率，即 p 值。"""
    if df <= 0 or chi2 < 0:
        return float("nan")
    if chi2 == 0:
        return 1.0
    a = df / 2.0
    x = chi2 / 2.0
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gser(a, x)))
    return max(0.0, min(1.0, _gcf(a, x)))


def _chi2(counts: list[int], expected: float, start: int = 1) -> dict[str, Any]:
    values = counts[start:]
    chi2 = sum((c - expected) ** 2 / expected for c in values) if expected > 0 else 0.0
    df = max(1, len(values) - 1)
    return {
        "chi2": round(chi2, 2),
        "df": df,
        "p": round(chi2_sf(chi2, df), 4),
    }


# ---------- 基础频率与遗漏 ----------
def frequency_stats(draws: list[dict[str, Any]]) -> tuple[list[int], list[int], dict[str, Any], dict[str, Any]]:
    n = len(draws)
    red_counts = [0] * (RED_MAX + 1)
    blue_counts = [0] * (BLUE_MAX + 1)
    for draw in draws:
        for num in parse_reds(draw):
            red_counts[num] += 1
        blue_counts[parse_blue(draw)] += 1

    red_expected = n * 6 / RED_MAX if n else 0.0
    blue_expected = n / BLUE_MAX if n else 0.0
    red = _chi2(red_counts, red_expected)
    red["expected"] = round(red_expected, 2)
    blue = _chi2(blue_counts, blue_expected)
    blue["expected"] = round(blue_expected, 2)
    return red_counts, blue_counts, red, blue


def _omission_one(hits: list[int], n: int) -> tuple[int, float, int]:
    if not hits:
        return n, float(n), n
    gaps = []
    prev = -1
    for hit in hits:
        gaps.append(hit - prev - 1)
        prev = hit
    current = n - 1 - hits[-1]
    gaps.append(current)
    count = len(hits)
    avg = (n - count) / count if count else float(n)
    return current, round(avg, 2), max(gaps)


def omission_stats(draws: list[dict[str, Any]]) -> tuple[dict[str, list], dict[str, list]]:
    n = len(draws)
    reds = [parse_reds(d) for d in draws]
    blues = [parse_blue(d) for d in draws]

    def pack(total: int, hits_fn: Callable[[int, int], bool]) -> dict[str, list]:
        cur = [0] * (total + 1)
        avg = [0.0] * (total + 1)
        mx = [0] * (total + 1)
        for num in range(1, total + 1):
            hits = [i for i in range(n) if hits_fn(i, num)]
            c, a, m = _omission_one(hits, n)
            cur[num], avg[num], mx[num] = c, a, m
        return {"current": cur, "avg": avg, "max": mx}

    red = pack(RED_MAX, lambda i, num: num in reds[i])
    blue = pack(BLUE_MAX, lambda i, num: blues[i] == num)
    return red, blue


# ---------- 形态 ----------
def _dist(counter: Counter, keys: Iterable[Any]) -> list[dict[str, Any]]:
    return [{"key": str(k), "n": int(counter.get(k, 0))} for k in keys]


def _ac(reds: list[int]) -> int:
    diffs = {b - a for i, a in enumerate(reds) for b in reds[i + 1:]}
    return len(diffs) - 5


def _span(reds: list[int]) -> int:
    return max(reds) - min(reds)


def _zones(reds: list[int]) -> tuple[int, int, int]:
    return (
        sum(1 for x in reds if x <= 11),
        sum(1 for x in reds if 12 <= x <= 22),
        sum(1 for x in reds if x >= 23),
    )


def _consecutive(reds: list[int]) -> int:
    return sum(1 for a, b in zip(reds, reds[1:]) if b - a == 1)


def sum_stats(draws: list[dict[str, Any]]) -> dict[str, Any]:
    sums = [sum(parse_reds(d)) for d in draws]
    bucket_counter = Counter()
    for value in sums:
        for low, high in SUM_BUCKETS:
            if low <= value <= high:
                bucket_counter[f"{low}-{high}"] += 1
                break
    recent = [{"c": d["c"], "v": sum(parse_reds(d))} for d in draws[-30:]]
    if not sums:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "buckets": [], "recent": recent}
    return {
        "mean": round(mean(sums), 2),
        "std": round(pstdev(sums), 2),
        "min": min(sums),
        "max": max(sums),
        "buckets": _dist(bucket_counter, [f"{a}-{b}" for a, b in SUM_BUCKETS]),
        "recent": recent,
    }


def shape_stats(draws: list[dict[str, Any]]) -> dict[str, Any]:
    odd_counter = Counter()
    big_counter = Counter()
    zone_counter = Counter()
    span_values: list[int] = []
    span_counter = Counter()
    ac_values: list[int] = []
    ac_counter = Counter()
    prime_counter = Counter()
    road_counter = Counter()
    tail_counter = Counter()
    same_tail_counter = Counter()
    consecutive_counter = Counter()
    repeat_counter = Counter()
    neighbor_counter = Counter()
    blue_big = Counter()
    blue_odd = Counter()
    blue_road = Counter()
    blue_tail = Counter()

    prev_reds: set[int] | None = None
    for draw in draws:
        reds = parse_reds(draw)
        red_set = set(reds)
        blue = parse_blue(draw)

        odd = sum(1 for x in reds if x % 2)
        odd_counter[odd] += 1
        big_counter[sum(1 for x in reds if x >= 17)] += 1
        zone_counter[_zones(reds)] += 1

        span = _span(reds)
        span_values.append(span)
        for low, high in SPAN_BUCKETS:
            if low <= span <= high:
                span_counter[f"{low}-{high}"] += 1
                break

        ac = _ac(reds)
        ac_values.append(ac)
        ac_counter[ac] += 1
        prime_counter[sum(1 for x in reds if x in PRIMES)] += 1

        roads = [0, 0, 0]
        for x in reds:
            roads[x % 3] += 1
        road_counter[tuple(roads)] += 1

        tails = [x % 10 for x in reds]
        tail_counter.update(tails)
        same_tail_counter[sum(1 for c in Counter(tails).values() if c >= 2)] += 1
        consecutive_counter[_consecutive(reds)] += 1

        if prev_reds is not None:
            repeat_counter[len(red_set & prev_reds)] += 1
            neighbors = {x - 1 for x in prev_reds} | {x + 1 for x in prev_reds}
            neighbor_counter[len(red_set & neighbors)] += 1

        blue_big["大(9-16)" if blue >= 9 else "小(1-8)"] += 1
        blue_odd["奇" if blue % 2 else "偶"] += 1
        blue_road[blue % 3] += 1
        blue_tail[blue % 10] += 1
        prev_reds = red_set

    return {
        "odd": _dist(odd_counter, range(0, 7)),
        "big": _dist(big_counter, range(0, 7)),
        "zone": sorted(
            [{"key": f"{a}:{b}:{c}", "n": n} for (a, b, c), n in zone_counter.items()],
            key=lambda x: (-x["n"], x["key"]),
        ),
        "span": {
            "mean": round(mean(span_values), 2) if span_values else 0,
            "buckets": _dist(span_counter, [f"{a}-{b}" for a, b in SPAN_BUCKETS]),
        },
        "ac": {
            "mean": round(mean(ac_values), 2) if ac_values else 0,
            "buckets": _dist(ac_counter, range(0, 11)),
        },
        "prime": _dist(prime_counter, range(0, 7)),
        "road": sorted(
            [{"key": f"{a}:{b}:{c}", "n": n} for (a, b, c), n in road_counter.items()],
            key=lambda x: (-x["n"], x["key"]),
        ),
        "tail": {
            "counts": [int(tail_counter.get(i, 0)) for i in range(10)],
            "same": _dist(same_tail_counter, range(0, 4)),
        },
        "consecutive": _dist(consecutive_counter, range(0, 6)),
        "repeat": _dist(repeat_counter, range(0, 7)),
        "neighbor": _dist(neighbor_counter, range(0, 7)),
        "blueShape": {
            "big": _dist(blue_big, ["小(1-8)", "大(9-16)"]),
            "odd": _dist(blue_odd, ["奇", "偶"]),
            "road": _dist(blue_road, [0, 1, 2]),
            "tail": [{"key": str(i), "n": int(blue_tail.get(i, 0))} for i in range(10)],
        },
    }


def cooccurrence_stats(draws: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = [[0] * (RED_MAX + 1) for _ in range(RED_MAX + 1)]
    for draw in draws:
        reds = parse_reds(draw)
        for i, a in enumerate(reds):
            for b in reds[i + 1:]:
                matrix[a][b] += 1
                matrix[b][a] += 1
    pairs = []
    for a in range(1, RED_MAX + 1):
        for b in range(a + 1, RED_MAX + 1):
            pairs.append({"a": a, "b": b, "n": matrix[a][b]})
    pairs.sort(key=lambda x: (-x["n"], x["a"], x["b"]))
    return {
        "matrix": matrix,
        "top": pairs[:12],
        "max": max((p["n"] for p in pairs), default=0),
    }


def build_stats(draws: list[dict[str, Any]], window: str = "all") -> dict[str, Any]:
    sliced = window_slice(draws, window)
    red_counts, blue_counts, red_chi, blue_chi = frequency_stats(sliced)
    red_omission, blue_omission = omission_stats(sliced)
    shapes = shape_stats(sliced)

    result: dict[str, Any] = {
        "window": str(window),
        "n": len(sliced),
        "range": {
            "first": sliced[0]["c"] if sliced else None,
            "last": sliced[-1]["c"] if sliced else None,
        },
        "red": {
            "counts": red_counts,
            "expected": red_chi.pop("expected"),
            **red_chi,
            "omission": red_omission,
        },
        "blue": {
            "counts": blue_counts,
            "expected": blue_chi.pop("expected"),
            **blue_chi,
            "omission": blue_omission,
        },
        "sum": sum_stats(sliced),
        "cooccurrence": cooccurrence_stats(sliced),
    }
    result.update(shapes)
    return result