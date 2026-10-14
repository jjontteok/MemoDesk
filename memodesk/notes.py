"""프로젝트별 메모 — 저장 · 상태 · 대기열 순서 · 한 번에 맡길 묶음.

    status   queued    대기 — 적으면 바로 여기 들어간다. 처리기가 **위에서부터** 차례로 AI 에게 맡긴다
             working   처리 중 — AI 작업이 이 메모를 들고 있다
             review    확인 대기 — AI 가 끝냈다. **사람이 결과를 보고** 닫거나 다시 맡긴다
             open      열림 — AI 가 못 했다(확인 필요 · 못 고침 …). 이유가 log 에 있다. **저절로 다시 돌지 않는다**
             done      완료

    kind     code      코드 — 클로드가 프로젝트 경로 안의 파일을 고친다
             human     사람 — AI 에게 맡기지 않는다. 처음부터 열림으로 두고 사람이 [완료]로 닫는다

AI 가 "고쳤다" 고 끝내도 바로 done 으로 두지 않는다 — 결과를 확인하는 것은 사람이다.
열림을 저절로 다시 돌리지 않는 이유 — 같은 이유로 또 못 하고 AI 비용만 든다.

**순서** — notes 배열 순서가 곧 처리 순서다. 처리기는 **같은 종류 연속 묶음**을 한 작업으로 가져간다(AI 호출 고정비를
줄이려고). 작업이 끝날 때마다 순서를 다시 읽으므로 도는 중에 끼워 넣거나 옮겨도 반영된다.
번호(M01 …)는 지워도 다시 쓰지 않는다 — 작업 기록 · 사용량이 번호로 메모를 가리킨다.

차시 작업대(content-pipeline `lesson_notes.py`)에서 가져왔다. 그림 · 검증 · 빌드 지점은 2차에 줄(lane)을 더할 때 넣는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
NOTES_NAME = "notes.json"
PREFIX = "M"
STATUSES = ("queued", "working", "review", "open", "done")
KINDS = ("code", "human")
HUMAN_KINDS = ("human",)
KIND_NAMES = {"code": "코드", "human": "사람"}
# 작업 줄 — 줄마다 한 번에 한 작업. 2차에 코덱스 줄(그림 · 검증)이 더해진다
LANE = {"code": "ai"}   # 메모는 고른 AI 하나가 처리한다(종류 구분 없음 — 2026-10-14 사용자 요청 "그냥 메모야")
BARRIERS: tuple[str, ...] = ()   # 칸막이 종류(위가 다 끝나야 돌고 아래는 이것을 기다린다) — 2차의 검증 · 빌드 지점

ATTACH_DIR = "attachments"   # data/projects/{id}/attachments/{메모 번호}/ — 메모에 붙여 넣은 그림
ATTACH_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ATTACH_MAX = 10
ATTACH_MAX_BYTES = 15 * 1024 * 1024


def now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _read(folder: Path) -> dict:
    path = folder / NOTES_NAME
    if not path.exists():
        return {"notes": [], "last_id": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"notes": [], "last_id": 0}
    return data if isinstance(data, dict) else {"notes": [], "last_id": 0}


def load(folder: Path) -> list[dict]:
    return _read(folder).get("notes", [])


def _number(note_id: str) -> int:
    return int(note_id[1:]) if note_id.startswith(PREFIX) and note_id[1:].isdigit() else 0


def save(folder: Path, notes: list[dict]) -> None:
    """임시 파일에 쓴 뒤 바꿔 끼운다 — 쓰다 꺼져도 notes.json 이 반쯤 남지 않게."""
    folder.mkdir(parents=True, exist_ok=True)
    last = max([_read(folder).get("last_id", 0)] + [_number(str(n.get("id", ""))) for n in notes])
    body = json.dumps({"notes": notes, "last_id": last}, ensure_ascii=False, indent=2) + "\n"
    tmp = folder / (NOTES_NAME + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(folder / NOTES_NAME)


def next_id(folder: Path, notes: list[dict]) -> str:
    last = max([_read(folder).get("last_id", 0)] + [_number(str(n.get("id", ""))) for n in notes])
    return f"{PREFIX}{last + 1:02d}"


def kind_of(note: dict) -> str:
    return note.get("kind") if note.get("kind") in KINDS else "code"


def _index(notes: list[dict], note_id: str | None) -> int | None:
    for i, note in enumerate(notes):
        if note["id"] == note_id:
            return i
    return None


def add(folder: Path, text: str, kind: str = "code", before: str | None = None, ai: str = "") -> dict:
    """대기열에 넣는다. before 가 있으면 그 메모 바로 앞, 없으면 맨 뒤. 사람 메모는 처음부터 열림.
    ai = 이 메모를 처리할 AI(2026-10-14 — 메모를 적을 때 추가한 AI 중 하나를 골라 보낸다)."""
    text = text.strip()
    if not text:
        raise ValueError("빈 메모")
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 종류: {kind}")
    notes = load(folder)
    human = kind in HUMAN_KINDS
    note = {"id": next_id(folder, notes), "kind": kind, "text": text, "status": "open" if human else "queued",
            "created_at": now(), "updated_at": now(),
            "log": [f"{now()} 사람이 처리할 메모 — AI 에게 맡기지 않음"] if human else []}
    if ai:
        note["ai"] = ai
    at = _index(notes, before) if before else None
    notes.insert(len(notes) if at is None else at, note)
    save(folder, notes)
    return note


def move(folder: Path, note_id: str, before: str | None) -> list[dict]:
    """대기 중인 메모를 옮긴다. before 메모 바로 앞으로, 없으면 맨 뒤로."""
    notes = load(folder)
    at = _index(notes, note_id)
    if at is None:
        raise ValueError(f"없는 메모: {note_id}")
    if notes[at]["status"] != "queued":
        raise ValueError("대기 중인 메모만 옮길 수 있다")
    if before == note_id:
        return notes
    note = notes.pop(at)
    target = _index(notes, before) if before else None
    notes.insert(len(notes) if target is None else target, note)
    save(folder, notes)
    return notes


def set_status(folder: Path, ids: list[str], status: str, message: str = "") -> list[dict]:
    if status not in STATUSES:
        raise ValueError(f"알 수 없는 상태: {status}")
    notes = load(folder)
    if status in ("queued", "working") and any(n["id"] in ids and kind_of(n) in HUMAN_KINDS for n in notes):
        raise ValueError("사람이 처리할 메모는 AI 에게 맡기지 않는다 — 맡기려면 종류를 코드로 바꾼다")
    for note in notes:
        if note["id"] in ids:
            note["status"] = status
            note["updated_at"] = now()
            if status in ("queued", "working"):
                note.pop("result", None)   # 다시 맡기면 지난 결과는 새 결과로 바뀐다 — 그사이 옛 결과를 보이지 않는다
            if message:
                note.setdefault("log", []).append(f"{now()} {message}")
    save(folder, notes)
    return notes


def set_result(folder: Path, note_id: str, status: str, result: dict, message: str = "") -> None:
    """AI 결과를 메모에 **구조로** 붙인다 — {kind, label, step, headline, detail, files, at, job}.
    카드는 headline 한 줄만 보이고 detail 은 접어 둔다."""
    notes = load(folder)
    for note in notes:
        if note["id"] == note_id:
            note["result"] = {**result, "at": now()}
    save(folder, notes)
    set_status(folder, [note_id], status, message)


def set_kind(folder: Path, note_id: str, kind: str) -> dict:
    """종류를 잘못 골랐을 때 고친다. 대기 중이면 종류만, 처리된 메모는 바꾼 종류로 다시 대기열에(사람으로 바꾸면 열림)."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 종류: {kind}")
    notes = load(folder)
    at = _index(notes, note_id)
    if at is None:
        raise ValueError(f"없는 메모: {note_id}")
    note = notes[at]
    if note["status"] == "working":
        raise ValueError("처리 중인 메모는 종류를 바꿀 수 없다 — 먼저 멈춘다")
    old = kind_of(note)
    if old == kind:
        return note
    note["kind"] = kind
    if kind in HUMAN_KINDS:
        note.pop("result", None)
    save(folder, notes)
    message = f"종류를 {KIND_NAMES[old]} → {KIND_NAMES[kind]} 로 바꿈"
    if kind in HUMAN_KINDS:
        set_status(folder, [note_id], "open", message + " — 사람이 처리")
    elif note["status"] == "queued":
        set_status(folder, [note_id], "queued", message)
    else:
        set_status(folder, [note_id], "queued", message + " — 다시 맡김")
    return note


def set_ai(folder: Path, note_id: str, ai: str) -> dict:
    """대기 중인 메모를 다른 AI 에게 보낸다. 처리 중이면 바꾸지 않는다(이미 그 AI 가 들고 있다)."""
    notes = load(folder)
    at = _index(notes, note_id)
    if at is None:
        raise ValueError(f"없는 메모: {note_id}")
    note = notes[at]
    if note["status"] == "working":
        raise ValueError("처리 중인 메모는 AI 를 바꿀 수 없다 — 끝난 뒤에 바꾼다")
    if note.get("ai") == ai:
        return note
    note["ai"] = ai
    save(folder, notes)
    set_status(folder, [note_id], note["status"], f"보낼 AI 를 {ai} 로 바꿈")
    return note


def edit_text(folder: Path, note_id: str, text: str) -> dict:
    """대기 중인 메모의 글을 고친다. AI 가 집어 간 뒤에는 고치지 않는다 — 프롬프트가 이미 나갔다."""
    text = text.strip()
    if not text:
        raise ValueError("메모 글이 비었다")
    notes = load(folder)
    at = _index(notes, note_id)
    if at is None:
        raise ValueError(f"없는 메모: {note_id}")
    note = notes[at]
    if note["status"] != "queued":
        raise ValueError("대기 중인 메모만 고칠 수 있다 — 이미 AI 가 처리를 시작했다")
    if note["text"] == text:
        return note
    note["text"] = text
    save(folder, notes)
    set_status(folder, [note_id], "queued", "사람이 글을 고침")
    return note


def refine(folder: Path, note_id: str, text: str, files: list[tuple[str, bytes]] | None = None) -> dict:
    """보완해서 다시 맡기기 — 원래 메모는 두고 보완 메모를 덧붙여 다시 대기열에 넣는다.
    AI 가 지난번에 무엇을 했는지 알아야 "조금 고쳐" 가 통하므로 지난 결과를 보완 기록에 함께 남긴다."""
    text = text.strip()
    if not text:
        raise ValueError("보완할 내용을 적어 주세요")
    if is_working(folder, note_id):
        raise ValueError("처리 중인 메모는 보완할 수 없다 — 끝난 뒤에 한다")
    notes = load(folder)
    at = _index(notes, note_id)
    if at is None:
        raise ValueError(f"없는 메모: {note_id}")
    note = notes[at]
    if kind_of(note) in HUMAN_KINDS:
        raise ValueError("사람이 처리할 메모다 — 맡기려면 종류를 코드로 바꾼다")
    prev = note.get("result") or {}
    refinements = note.setdefault("refinements", [])
    entry = {"at": now(), "text": text, "prev": {k: prev[k] for k in ("label", "headline", "detail", "files") if prev.get(k)}}
    if files:
        entry["images"] = _save_images(folder, note_id, f"r{len(refinements) + 1}-img", files)
    refinements.append(entry)
    save(folder, notes)
    set_status(folder, [note_id], "queued", f"사람이 보완해 다시 맡김 — {text[:40]}")
    return note


def attach(folder: Path, note_id: str, files: list[tuple[str, bytes]]) -> list[str]:
    """메모에 그림을 붙인다(메모 칸에 캡처를 붙여 넣기). 메모의 `images` 에 프로젝트 기록 폴더 기준 경로를 적는다."""
    notes = load(folder)
    note = next((n for n in notes if n["id"] == note_id), None)
    if note is None:
        raise ValueError(f"없는 메모: {note_id}")
    saved = list(note.get("images") or [])
    note["images"] = saved + _save_images(folder, note_id, "img", files, start=len(saved) + 1)
    save(folder, notes)
    return note["images"]


def _save_images(folder: Path, note_id: str, prefix: str, files: list[tuple[str, bytes]], start: int = 1) -> list[str]:
    """그림을 `attachments/{메모}/{prefix}-N.확장자` 로 저장한다. 전부 검사한 뒤에 쓴다(반쯤 저장하지 않게)."""
    if len(files) > ATTACH_MAX:
        raise ValueError(f"그림은 한 번에 {ATTACH_MAX}장까지")
    checked = []
    for name, blob in files:
        suffix = Path(name).suffix.lower() or ".png"
        if suffix not in ATTACH_SUFFIXES:
            raise ValueError(f"그림 파일이 아니다: {name}")
        if len(blob) > ATTACH_MAX_BYTES:
            raise ValueError(f"그림이 너무 크다(15MB 까지): {name}")
        checked.append((suffix, blob))
    target_dir = folder / ATTACH_DIR / note_id
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, (suffix, blob) in enumerate(checked, start):
        target = target_dir / f"{prefix}-{i}{suffix}"
        target.write_bytes(blob)
        saved.append(target.relative_to(folder).as_posix())
    return saved


def prompt_block(note: dict, folder: Path | None = None) -> str:
    """AI 에게 넘길 메모 한 건 — 원래 메모(붙인 그림 경로 포함), 보완했으면 지난 결과와 보완 메모를 차례로."""
    parts = [f"### {note['id']}", "", note["text"].strip()]
    base = folder.resolve() if folder else None
    where = lambda rels: [f"- {base / rel if base else rel}" for rel in rels]   # noqa: E731
    if note.get("images"):
        parts += ["", "사람이 이 메모에 붙인 그림(화면 캡처 등) — **직접 열어 보고** 메모가 가리키는 자리를 확인한다:",
                  *where(note["images"])]
    for i, ref in enumerate(note.get("refinements") or [], 1):
        prev = ref.get("prev") or {}
        parts += ["", f"#### 보완 {i} — 지난번 결과를 보고 사람이 덧붙인 것. 원래 메모와 함께 이것을 반영한다"]
        if prev:
            parts.append(f"지난번 결과: {prev.get('label', '')} — {prev.get('headline', '')}".strip())
            if prev.get("files"):
                parts.append("지난번에 바꾼 파일: " + ", ".join(prev["files"]))
            if prev.get("detail"):
                parts += ["지난번 설명:", prev["detail"].strip()]
        parts += ["보완 메모:", ref["text"].strip()]
        if ref.get("images"):
            parts += ["이 보완에 붙인 그림 — **직접 열어 보고** 보완 메모가 가리키는 자리를 확인한다:", *where(ref["images"])]
    return "\n".join(parts)


def is_working(folder: Path, note_id: str) -> bool:
    """AI 가 들고 있는 메모인가 — 들고 있는 동안은 지우거나 상태 · 종류를 바꾸지 않는다."""
    return any(n["id"] == note_id and n["status"] == "working" for n in load(folder))


def remove(folder: Path, note_id: str) -> list[dict]:
    if is_working(folder, note_id):
        raise ValueError("처리 중인 메모는 지울 수 없다 — 먼저 멈춘다")
    notes = [n for n in load(folder) if n["id"] != note_id]
    save(folder, notes)
    return notes


def release_working(folder: Path, message: str, to: str = "open", ids: list[str] | None = None) -> None:
    """작업이 끊겼을 때 들고 있던 메모를 되돌린다(멈춤이면 대기로, 실패면 열림으로). ids 를 주면 그 메모만."""
    held = [n["id"] for n in load(folder) if n["status"] == "working" and (ids is None or n["id"] in ids)]
    if held:
        set_status(folder, held, to, message)


def runnable_groups(notes: list[dict], busy: set[str] | frozenset[str] = frozenset()) -> list[tuple[str, list[dict]]]:
    """지금 시작할 수 있는 묶음 [(줄, 메모들)]. busy 는 작업이 도는 줄.

    줄이 다르면 서로 기다리지 않는다. 칸막이(BARRIERS)는 앞에 걸린 것이 없고 모든 줄이 쉴 때만 돌고, 뒤의 것은
    그것이 끝날 때까지 기다린다. 묶음은 걸린 메모부터 **이어지는 같은 종류 · 같은 AI 대기 메모**다(처리 중 · 다른 종류 · 다른 AI 에서 끊는다).
    AI 가 달라도 한 프로젝트에서는 한 줄로 차례대로 돈다 — 두 AI 가 같은 폴더를 함께 고치면 한쪽을 되돌릴 때 다른 쪽이 고친 것까지 지운다.
    """
    busy = set(busy)
    pending = [n for n in notes if n.get("status") in ("queued", "working") and kind_of(n) in LANE]
    out: list[tuple[str, list[dict]]] = []
    before: list[str] = []
    for i, note in enumerate(pending):
        kind = kind_of(note)
        lane = LANE[kind]
        if note["status"] == "queued" and lane not in busy:
            ok = (not before and not busy) if kind in BARRIERS else not any(k in BARRIERS for k in before)
            if ok:
                group = [note]
                for later in pending[i + 1:]:
                    if later["status"] != "queued" or kind_of(later) != kind or later.get("ai") != note.get("ai"):
                        break
                    group.append(later)
                out.append((lane, group))
                busy.add(lane)
        before.append(kind)
    return out


def has_queued(notes: list[dict]) -> bool:
    return any(n.get("status") == "queued" for n in notes)
