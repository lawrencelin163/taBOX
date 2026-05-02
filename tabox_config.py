from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent

#如果有多個 taBOX_M*.json，會取字母順序第一個的作為配置文件，否則默認使用 taBOX.json
def _find_config_file() -> Path:
    candidates = sorted(PROJECT_ROOT.glob("taBOX_M*.json"))
    if candidates:
        return candidates[0]
    return PROJECT_ROOT / "taBOX.json"

CONFIG_FILE = _find_config_file()


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        print(f'"CONFIG file not found. 請確保 taBOX.json 配置文件存在於 {CONFIG_FILE}. exit(1).')
        raise SystemExit(1)

    with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
        loaded = json.load(config_file)

    if not isinstance(loaded, dict):
        raise RuntimeError("taBOX.json must contain a JSON object at the top level")

    return loaded


def save_config(config_data: dict[str, Any]) -> None:
    with CONFIG_FILE.open("w", encoding="utf-8") as config_file:
        json.dump(config_data, config_file, ensure_ascii=False, indent=2)
        config_file.write("\n")
    load_config.cache_clear()


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path