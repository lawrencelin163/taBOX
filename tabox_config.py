from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "taBOX.json"


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