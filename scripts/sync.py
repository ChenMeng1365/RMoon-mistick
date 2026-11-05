# coding: utf-8
"""命令行同步开奖数据：python scripts/sync.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config  # noqa: E402
from app.store import DrawStore  # noqa: E402
from app.upstream import Upstream, UpstreamError  # noqa: E402


def main() -> int:
    config = load_config()
    store = DrawStore(config.data_path)
    print(f"数据文件: {config.data_path}")
    print(f"同步前: {store.count()} 期")
    try:
        result = Upstream(config.request_timeout).sync(store)
    except UpstreamError as exc:
        print(f"同步失败: {exc}")
        return 1
    print(
        f"同步完成: {result['count']} 期，新增 {result['added']} 期，"
        f"官方 {result['official']} 条，早期 {result['early']} 条，"
        f"{result['elapsed_ms']}ms"
    )
    for error in result.get("errors") or []:
        print(f"警告: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())