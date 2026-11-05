# coding: utf-8
"""一键验证：数据完整性 + 单元测试。python scripts/verify.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics import build_stats  # noqa: E402
from app.config import load_config  # noqa: E402
from app.store import DrawStore  # noqa: E402


def check_data() -> bool:
    config = load_config()
    store = DrawStore(config.data_path)
    draws = store.load()
    print(f"数据文件: {config.data_path}")
    print(f"期数: {len(draws)}")
    if len(draws) < 100:
        print("FAIL: 开奖库不足 100 期")
        return False

    seen = set()
    for draw in draws:
        reds = [int(x) for x in draw["r"].split(",")]
        blue = int(draw["b"])
        if len(reds) != 6 or len(set(reds)) != 6 or not all(1 <= n <= 33 for n in reds):
            print(f"FAIL: 红球不合法 {draw}")
            return False
        if not 1 <= blue <= 16:
            print(f"FAIL: 蓝球不合法 {draw}")
            return False
        if draw["c"] in seen:
            print(f"FAIL: 期号重复 {draw['c']}")
            return False
        seen.add(draw["c"])

    stats = build_stats(draws, "all")
    print(f"范围: {stats['range']['first']} ~ {stats['range']['last']}")
    print(f"和值均值: {stats['sum']['mean']}，标准差: {stats['sum']['std']}")
    print(f"红球 χ²: {stats['red']['chi2']}，p={stats['red']['p']}")
    print(f"蓝球 χ²: {stats['blue']['chi2']}，p={stats['blue']['p']}")
    return True


def main() -> int:
    if not check_data():
        return 1

    print("\n运行单元测试…")
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())