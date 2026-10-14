"""AI 호출마다 **토큰 · 비용 · 시간**을 프로젝트 기록 폴더에 적는다(`usage-log.jsonl`).

어느 폴더에 적을지는 작업 스크립트가 `bind(folder, tag=작업 번호)` 로 정한다 — 묶지 않으면 아무것도 안 한다.
작업 번호(tag)로 작업 기록(jobs.jsonl)과 잇는다.

    claude usage.input_tokens(캐시 제외) · cache_read_input_tokens · cache_creation_input_tokens · output_tokens + total_cost_usd
    →      input(캐시 포함 전체) · cached(캐시에서 읽은 것) · output · cost_usd
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from memodesk.notes import KST

LOG_NAME = "usage-log.jsonl"

_lock = threading.Lock()
_folder: Path | None = None
_tag = ""


def bind(folder: Path, tag: str = "") -> None:
    global _folder, _tag
    _folder = folder
    _tag = tag


def normalize(usage: dict | None) -> dict:
    if not isinstance(usage, dict):
        return {"input": None, "cached": None, "output": None, "cost_usd": None}
    raw = usage.get("usage") or {}
    fresh = int(raw.get("input_tokens") or 0)
    read = int(raw.get("cache_read_input_tokens") or 0)
    write = int(raw.get("cache_creation_input_tokens") or 0)
    return {"input": fresh + read + write, "cached": read, "output": int(raw.get("output_tokens") or 0),
            "cost_usd": usage.get("total_cost_usd")}


def record_call(stage: str | None, provider: str, model: str | None, seconds: float, usage: dict | None,
                ok: bool, error: str = "") -> None:
    if _folder is None:
        return
    record = {"at": datetime.now(KST).isoformat(timespec="seconds"), **({"tag": _tag} if _tag else {}),
              "kind": "llm", "stage": stage or "?", "provider": provider, "model": model or "default",
              "seconds": round(seconds, 1), "ok": ok, "error": " ".join(error.split())[:160], **normalize(usage)}
    with _lock:
        _folder.mkdir(parents=True, exist_ok=True)
        with (_folder / LOG_NAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
