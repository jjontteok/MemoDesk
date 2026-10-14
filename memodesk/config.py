"""설정 파일(`data/config.json`) — 포트 · 알림 · AI 모델 · 프로젝트 목록.

`data/` 는 PC 마다 다른 기록이라 git 에 올리지 않는다. 환경 변수 `MEMODESK_DATA` 로 다른 곳을 쓸 수 있다(시험용).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ["MEMODESK_DATA"]).resolve() if os.environ.get("MEMODESK_DATA") else APP_DIR / "data"
CONFIG = DATA_DIR / "config.json"
DEFAULT_PORT = 8791

DEFAULTS = {"port": DEFAULT_PORT, "notify": True, "claude_model": "", "claude_effort": "", "projects": []}

_lock = threading.RLock()


def load() -> dict:
    with _lock:
        try:
            saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
        except json.JSONDecodeError:
            saved = {}
        return {**DEFAULTS, **(saved if isinstance(saved, dict) else {})}


def save(data: dict) -> None:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CONFIG)


def update(**changes) -> dict:
    with _lock:
        data = load()
        data.update(changes)
        save(data)
        return data
