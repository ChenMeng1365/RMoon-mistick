# coding: utf-8
"""配置加载：config.json -> 环境变量 -> 命令行，后者覆盖前者。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"

ENV_MAP = {
    "MISTICK_HOST": "host",
    "MISTICK_PORT": "port",
    "MISTICK_DATA_FILE": "data_file",
    "MISTICK_STATIC_DIR": "static_dir",
    "MISTICK_LOG_DIR": "log_dir",
    "MISTICK_AUTO_SYNC": "auto_sync",
    "MISTICK_SYNC_INTERVAL_HOURS": "sync_interval_hours",
    "MISTICK_REQUEST_TIMEOUT": "request_timeout",
}


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 3100
    data_file: str = "data/draws.json"
    static_dir: str = "static"
    log_dir: str = "logs"
    auto_sync: bool = False
    sync_interval_hours: float = 24.0
    request_timeout: int = 30
    first_prize: int = 7_000_000
    second_prize: int = 200_000
    max_body_bytes: int = 1_048_576

    def path(self, value: str) -> Path:
        """把配置里的相对路径解析到项目根目录。"""
        p = Path(value)
        return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()

    @property
    def data_path(self) -> Path:
        return self.path(self.data_file)

    @property
    def static_path(self) -> Path:
        return self.path(self.static_dir)

    @property
    def log_path(self) -> Path:
        return self.path(self.log_dir)

    def validate(self) -> None:
        if not (1 <= int(self.port) <= 65535):
            raise ValueError("port 必须在 1-65535 之间")
        if float(self.sync_interval_hours) <= 0:
            raise ValueError("sync_interval_hours 必须大于 0")
        if int(self.request_timeout) <= 0:
            raise ValueError("request_timeout 必须大于 0")


def _coerce(name: str, value: Any) -> Any:
    if name in ("port", "request_timeout", "first_prize", "second_prize", "max_body_bytes"):
        return int(value)
    if name == "sync_interval_hours":
        return float(value)
    if name == "auto_sync":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    return str(value)


def load_config(config_path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    """读取配置。overrides 一般来自命令行参数。"""
    raw: dict[str, Any] = {}
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            raw.update(json.load(fh))

    for env_key, field_name in ENV_MAP.items():
        if env_key in os.environ:
            raw[field_name] = os.environ[env_key]

    if overrides:
        raw.update({k: v for k, v in overrides.items() if v is not None})

    allowed = {f.name for f in fields(Config)}
    kwargs = {k: _coerce(k, v) for k, v in raw.items() if k in allowed}
    cfg = Config(**kwargs)
    cfg.validate()
    return cfg