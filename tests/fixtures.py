# coding: utf-8
"""测试共用的合成开奖数据。"""

from __future__ import annotations

import datetime as dt
from typing import Any


def make_draws(n: int = 100, start_code: int = 2_003_001) -> list[dict[str, Any]]:
    draws: list[dict[str, Any]] = []
    day = dt.date(2003, 2, 23)
    for i in range(n):
        reds = sorted({((i * 7 + j * 5) % 33) + 1 for j in range(6)})
        blue = (i * 3) % 16 + 1
        draws.append(
            {
                "c": str(start_code + i),
                "d": (day + dt.timedelta(days=i)).isoformat(),
                "r": ",".join(f"{x:02d}" for x in reds),
                "b": f"{blue:02d}",
                "p": None,
                "s": None,
            }
        )
    return draws