# coding: utf-8
"""HTTP 服务：静态托管 + JSON API + 请求日志。"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .api import ApiError, App
from .config import Config, load_config

LOGGER = logging.getLogger("mistick")
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def setup_logging(config: Config) -> None:
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    LOGGER.addHandler(stream)

    try:
        config.log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            config.log_path / "mistick.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        LOGGER.addHandler(file_handler)
    except OSError:
        LOGGER.warning("日志目录不可写，仅输出到控制台")


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    static_root = app.config.static_path

    class Handler(BaseHTTPRequestHandler):
        server_version = f"mistick/{__version__}"
        protocol_version = "HTTP/1.1"

        # ---------- 基础响应 ----------
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def send_error_json(self, status: int, message: str) -> None:
            self.send_json({"ok": False, "message": message}, status)

        def send_static(self, path: str, head_only: bool = False) -> None:
            relative = unquote(path).lstrip("/") or "index.html"
            candidate = (static_root / relative).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                self.send_error_json(403, "禁止访问")
                return
            if candidate.is_dir():
                candidate = candidate / "index.html"
            if not candidate.is_file():
                self.send_error_json(404, "页面不存在")
                return
            try:
                body = candidate.read_bytes()
            except OSError:
                self.send_error_json(500, "读取静态文件失败")
                return
            ctype = STATIC_TYPES.get(candidate.suffix.lower())
            if not ctype:
                ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Cache-Control",
                "no-cache",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors()
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

        # ---------- 请求体 ----------
        def read_json(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if length > app.config.max_body_bytes:
                raise ApiError(413, "请求体过大")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApiError(400, "请求体不是合法 JSON") from exc

        # ---------- 路由 ----------
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_HEAD(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cors()
                self.end_headers()
            else:
                self.send_static(parsed.path, head_only=True)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api("GET", parsed.path, parse_qs(parsed.query), None)
            else:
                self.send_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                self.send_error_json(404, "接口不存在")
                return
            try:
                body = self.read_json()
                self._handle_api("POST", parsed.path, parse_qs(parsed.query), body)
            except ApiError as exc:
                self.send_error_json(exc.status, exc.message)
            except Exception:
                LOGGER.exception("处理 POST 请求失败: %s", self.path)
                self.send_error_json(500, "服务器内部错误")

        def _handle_api(self, method: str, path: str, query: dict[str, list[str]], body: Any) -> None:
            started = time.perf_counter()
            try:
                if method == "GET" and path == "/api/health":
                    payload = app.health()
                elif method == "GET" and path == "/api/meta":
                    payload = app.meta()
                elif method == "GET" and path == "/api/config":
                    payload = app.config_payload()
                elif method == "GET" and path == "/api/draws":
                    payload = app.draws(query)
                elif method == "GET" and path == "/api/stats":
                    payload = app.stats(query)
                elif method == "POST" and path == "/api/generate":
                    payload = app.generate(body)
                elif method == "POST" and path == "/api/backtest":
                    payload = app.backtest(body)
                elif method == "POST" and path == "/api/wheel":
                    payload = app.wheel(body)
                elif method == "POST" and path == "/api/sync":
                    payload = app.sync()
                else:
                    raise ApiError(404, "接口不存在")
                payload.setdefault("ok", True)
                self.send_json(payload)
            except ApiError as exc:
                self.send_error_json(exc.status, exc.message)
            except Exception:
                LOGGER.exception("API 处理失败: %s %s", method, path)
                self.send_error_json(500, "服务器内部错误")
            finally:
                cost = (time.perf_counter() - started) * 1000
                if cost > 200:
                    LOGGER.info("%s %s %.0fms", method, path, cost)

        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def create_server(config: Config, app: App) -> ThreadingHTTPServer:
    handler = make_handler(app)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    server.daemon_threads = True
    return server


def _auto_sync_loop(app: App) -> None:
    interval = max(60.0, app.config.sync_interval_hours * 3600)
    LOGGER.info("自动同步已开启，间隔 %.1f 小时", app.config.sync_interval_hours)
    while not app._auto_stop.wait(interval):
        try:
            result = app.sync()
            LOGGER.info("自动同步完成: %s 期，新增 %s", result.get("count"), result.get("added"))
        except Exception as exc:
            LOGGER.warning("自动同步失败: %s", exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="mistick 双色球选号台")
    parser.add_argument("--config", help="配置文件路径，默认 config.json")
    parser.add_argument("--host", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, help="监听端口，默认 3100")
    args = parser.parse_args(argv)

    config = load_config(args.config, {"host": args.host, "port": args.port})
    setup_logging(config)

    app = App(config)
    try:
        meta = app.meta()
        LOGGER.info("开奖库: %s 期，%s ~ %s", meta["count"],
                    meta["first"]["c"] if meta["first"] else "-",
                    meta["last"]["c"] if meta["last"] else "-")
    except Exception as exc:
        LOGGER.error("开奖库读取失败: %s", exc)

    try:
        server = create_server(config, app)
    except OSError as exc:
        LOGGER.error("启动失败: %s", exc)
        print(f"启动失败：{exc}")
        print(f"请确认端口 {config.port} 未被占用，或用 --port 指定其他端口。")
        return

    actual_port = server.server_address[1]
    print(f"mistick {__version__} 已启动: http://{config.host}:{actual_port}/")
    print(f"数据文件: {config.data_path}")
    print("按 Ctrl+C 停止服务")

    if config.auto_sync:
        threading.Thread(target=_auto_sync_loop, args=(app,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止…")
    finally:
        app._auto_stop.set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()