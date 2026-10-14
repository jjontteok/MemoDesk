"""작업이 실패했을 때 로그에서 **사람이 할 일**을 찾아 한 줄로 알려 준다.

알려진 문구만 본다. 모르는 실패는 빈 문자열 — 화면은 "○○ 실패 (종료 코드 N)" 과 로그를 보여 준다.
로그 전체가 아니라 **오류로 볼 줄만** 대조한다 — AI 가 읽은 파일 내용(문서에 적힌 오류 문구 예시 등)이 로그에 남아
실제 원인보다 먼저 맞는 일이 있었다(차시 작업대 실측 2026-10-13).
"""

from __future__ import annotations

import json
from pathlib import Path

# (로그에 이 문구 중 하나가 있으면, 사람에게 보일 이유와 할 일) — 위에서부터 먼저 맞는 것
PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("Invalid API key", "Please run /login", "OAuth token has expired", "authentication_error", "Not logged in",
      "refresh_token_invalidated", "token_revoked", "Please log in again", "Please set an Auth method"),
     "AI 계정 로그인이 끊겼습니다 — 왼쪽 [환경 점검]에서 다시 로그인한 뒤 [다시 맡기기]"),
    (("usage limit", "rate_limit_error", "Rate limit reached", "hit your limit", "RESOURCE_EXHAUSTED", "Quota exceeded"),
     "AI 사용 한도에 걸렸습니다 — 한도가 풀린 뒤 [다시 맡기기]"),
    (("overloaded_error", "at capacity"),
     "AI 서버가 혼잡합니다 — 잠시 뒤 [다시 맡기기]"),
    (("timed out in non-interactive", "TimeoutExpired", "TimeoutError"),
     "AI 가 제한 시간 안에 끝내지 못했습니다 — 메모를 나눠 적어 [다시 맡기기]"),
    (("백업할 크기가 상한",),
     "프로젝트가 너무 커서 백업을 못 했습니다 — [설정]에서 백업 제외 목록을 늘리세요"),
    (("is not recognized as an internal or external command", "command not found", "[WinError 2]"),
     "AI 프로그램을 찾지 못했습니다 — 왼쪽 [환경 점검]에서 설치를 확인하세요"),
]


def reason(log_text: str) -> str:
    text = error_lines(log_text)
    for needles, message in PATTERNS:
        if any(needle in text for needle in needles):
            return message
    return ""


def error_lines(log_text: str) -> str:
    """JSON 이벤트(AI CLI 출력)는 오류 이벤트만 남긴다. JSON 이 아닌 줄(파이썬 오류 · 작업대 줄)은 그대로 둔다."""
    kept = []
    for line in log_text.splitlines():
        body = line.strip()
        if body.startswith("stdout: "):
            body = body[len("stdout: "):]
        if not body.startswith("{"):
            kept.append(line)
            continue
        try:
            event = json.loads(body)
        except ValueError:
            kept.append(line)
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if event.get("type") in ("error", "turn.failed") or event.get("is_error") is True \
                or (isinstance(item, dict) and item.get("type") == "error"):
            kept.append(line)
    return "\n".join(kept)


def reason_from_log(path: Path) -> str:
    if not path.exists():
        return ""
    return reason(path.read_text(encoding="utf-8", errors="replace"))
