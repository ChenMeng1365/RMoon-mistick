# coding: utf-8
"""上游数据同步：福彩官方（2013+） + 500 网（2003-2012）。"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .store import DrawStore, normalize_draw

OFFICIAL_URL = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    "?name=ssq&issueCount=99999"
)
EARLY_URL = "https://datachart.500.com/ssq/history/newinc/history.php?start=03001&end=12154"

OFFICIAL_HEADERS = {
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
EARLY_HEADERS = {
    "Referer": "https://datachart.500.com/ssq/",
    "User-Agent": OFFICIAL_HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

EARLY_ROW_RE = re.compile(
    r"<td>(\d{5})</td>((?:<td class=\"t_cfont2\">\d{2}</td>){6})"
    r"<td class=\"t_cfont4\">(\d{2})</td>.*?<td>(\d{4}-\d{2}-\d{2})</td>",
    re.S,
)


class UpstreamError(Exception):
    """上游不可用或返回格式变化。"""


def _fetch(url: str, headers: dict[str, str], timeout: int, retries: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise UpstreamError(f"HTTP {resp.status}")
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError, UpstreamError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise UpstreamError(f"请求失败: {last_error}")


def fetch_official(timeout: int = 30) -> list[dict[str, Any]]:
    raw = _fetch(OFFICIAL_URL, OFFICIAL_HEADERS, timeout)
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise UpstreamError(f"官方接口不是合法 JSON: {exc}") from exc

    if payload.get("state") != 0:
        raise UpstreamError(f"官方接口返回 state={payload.get('state')} {payload.get('message', '')}")

    rows = payload.get("result") or []
    draws: list[dict[str, Any]] = []
    for row in rows:
        try:
            draws.append(
                normalize_draw(
                    {
                        "c": row.get("code"),
                        "d": str(row.get("date", "")).split("(")[0],
                        "r": row.get("red"),
                        "b": row.get("blue"),
                        "p": row.get("poolmoney"),
                        "s": row.get("sales"),
                    }
                )
            )
        except Exception:
            continue
    if not draws:
        raise UpstreamError("官方接口返回 0 条有效记录")
    return draws


def _decode_html(raw: bytes) -> str:
    for encoding in ("gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_early(timeout: int = 30) -> list[dict[str, Any]]:
    raw = _fetch(EARLY_URL, EARLY_HEADERS, timeout)
    text = _decode_html(raw)
    draws: list[dict[str, Any]] = []
    for code5, red_html, blue, date in EARLY_ROW_RE.findall(text):
        reds = re.findall(r"\d{2}", red_html)
        if len(reds) != 6:
            continue
        try:
            draw = normalize_draw(
                {
                    "c": "20" + code5,
                    "d": date,
                    "r": ",".join(reds),
                    "b": blue,
                    "p": None,
                    "s": None,
                }
            )
        except Exception:
            continue
        if draw["c"] < "2013001":
            draws.append(draw)
    if not draws:
        raise UpstreamError("500 网未解析到早期记录（页面结构可能已变化）")
    return draws


class Upstream:
    def __init__(self, timeout: int = 30):
        self.timeout = max(5, int(timeout))

    def sync(self, store: DrawStore) -> dict[str, Any]:
        started = time.perf_counter()
        errors: list[str] = []
        official: list[dict[str, Any]] = []
        early: list[dict[str, Any]] = []

        try:
            official = fetch_official(self.timeout)
        except UpstreamError as exc:
            errors.append(f"官方: {exc}")

        try:
            early = fetch_early(self.timeout)
        except UpstreamError as exc:
            errors.append(f"500网: {exc}")

        if not official and not early:
            raise UpstreamError("；".join(errors) or "双源均无数据")

        merged = store.merge(official + early, prefer_new=True)
        return {
            "ok": True,
            "count": merged["count"],
            "added": merged["added"],
            "accepted": merged["accepted"],
            "official": len(official),
            "early": len(early),
            "first": merged["first"],
            "last": merged["last"],
            "errors": errors,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }