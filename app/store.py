# coding: utf-8
"""开奖库读写。文件即数据库，进程内缓存 + 原子替换。"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Iterable

CODE_RE = re.compile(r"^\d{7}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StoreError(Exception):
    """数据文件损坏或格式不合法。"""


def _to_int(value: Any) -> int | None:
    if value in (None, "", "0", 0):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def normalize_draw(item: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化一条开奖记录，输出字段与旧库保持一致。"""
    code = str(item.get("c", "")).strip()
    if not CODE_RE.match(code):
        raise StoreError(f"期号不合法: {code!r}")

    date = str(item.get("d", "")).strip()[:10]
    if not DATE_RE.match(date):
        raise StoreError(f"日期不合法: {date!r}")

    raw_red = str(item.get("r", ""))
    try:
        reds = sorted({int(x) for x in re.split(r"[,\s]+", raw_red.strip()) if x})
    except ValueError as exc:
        raise StoreError(f"红球不合法: {raw_red!r}") from exc
    if len(reds) != 6 or reds[0] < 1 or reds[-1] > 33:
        raise StoreError(f"红球必须是 6 个 1-33 的不重复数字: {raw_red!r}")

    try:
        blue = int(item.get("b"))
    except (TypeError, ValueError) as exc:
        raise StoreError(f"蓝球不合法: {item.get('b')!r}") from exc
    if not 1 <= blue <= 16:
        raise StoreError(f"蓝球必须在 1-16: {blue}")

    return {
        "c": code,
        "d": date,
        "r": ",".join(f"{n:02d}" for n in reds),
        "b": f"{blue:02d}",
        "p": _to_int(item.get("p")),
        "s": _to_int(item.get("s")),
    }


class DrawStore:
    """线程安全的开奖库。

    - 读取：带 mtime 校验的进程内缓存，sync 后自动失效。
    - 写入：先写 .tmp 再 os.replace，避免半截文件。
    - 合并：按期号去重，默认新数据覆盖旧数据。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._draws: list[dict[str, Any]] = []
        self._updated_at: int = 0
        self._mtime: float = -1.0
        self._loaded = False

    # ---------- 读 ----------
    def _read_file(self) -> tuple[list[dict[str, Any]], int]:
        if not self.path.exists():
            return [], 0
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"读取开奖库失败: {exc}") from exc

        if isinstance(payload, list):
            raw_draws, updated_at = payload, 0
        elif isinstance(payload, dict):
            raw_draws = payload.get("draws", [])
            updated_at = int(payload.get("t") or 0)
        else:
            raise StoreError("开奖库格式不正确")

        if not isinstance(raw_draws, list):
            raise StoreError("开奖库 draws 字段不是数组")

        draws: list[dict[str, Any]] = []
        for item in raw_draws:
            if not isinstance(item, dict):
                continue
            try:
                draws.append(normalize_draw(item))
            except StoreError:
                # 单条坏数据不拖垮整库，写日志由上层负责
                continue
        draws.sort(key=lambda d: int(d["c"]))
        return draws, updated_at

    def load(self, force: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            if self.path.exists():
                mtime = self.path.stat().st_mtime
            else:
                mtime = 0.0
            if force or not self._loaded or mtime != self._mtime:
                self._draws, self._updated_at = self._read_file()
                self._mtime = mtime
                self._loaded = True
            return list(self._draws)

    def all(self) -> list[dict[str, Any]]:
        return self.load()

    def count(self) -> int:
        return len(self.load())

    def meta(self) -> dict[str, Any]:
        draws = self.load()
        if not draws:
            return {"count": 0, "first": None, "last": None, "updated_at": self._updated_at}
        return {
            "count": len(draws),
            "first": {"c": draws[0]["c"], "d": draws[0]["d"]},
            "last": {"c": draws[-1]["c"], "d": draws[-1]["d"]},
            "updated_at": self._updated_at,
        }

    def recent(self, limit: int = 30, offset: int = 0, order: str = "desc") -> dict[str, Any]:
        draws = self.load()
        total = len(draws)
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        ordered = list(reversed(draws)) if order == "desc" else draws
        items = ordered[offset:offset + limit]
        return {"total": total, "items": items, "limit": limit, "offset": offset, "order": order}

    def latest(self) -> dict[str, Any] | None:
        draws = self.load()
        return draws[-1] if draws else None

    # ---------- 写 ----------
    def _write_file(self, draws: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "t": int(time.time()),
            "count": len(draws),
            "draws": draws,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def merge(self, incoming: Iterable[dict[str, Any]], prefer_new: bool = True) -> dict[str, Any]:
        """合并开奖记录，返回新增/更新统计。"""
        with self._lock:
            current = self.load()
            by_code = {d["c"]: d for d in current}
            before = set(by_code)
            accepted = 0
            for item in incoming:
                draw = normalize_draw(item)
                if draw["c"] not in by_code or prefer_new:
                    by_code[draw["c"]] = draw
                    accepted += 1
            merged = sorted(by_code.values(), key=lambda d: int(d["c"]))
            self._write_file(merged)
            self._draws = merged
            self._updated_at = int(time.time())
            self._mtime = self.path.stat().st_mtime
            self._loaded = True
            added = len(set(by_code) - before)
            return {
                "count": len(merged),
                "accepted": accepted,
                "added": added,
                "first": merged[0]["c"] if merged else None,
                "last": merged[-1]["c"] if merged else None,
            }

    def replace(self, draws: Iterable[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            normalized = sorted((normalize_draw(d) for d in draws), key=lambda d: int(d["c"]))
            self._write_file(normalized)
            self._draws = normalized
            self._updated_at = int(time.time())
            self._mtime = self.path.stat().st_mtime
            self._loaded = True
            return {"count": len(normalized)}