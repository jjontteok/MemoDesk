"""MemoDesk 서버 — 화면(web/)과 API. 이 PC 에서만 듣는다(127.0.0.1).

    python -B -m memodesk               # http://127.0.0.1:8791
    python -B -m memodesk --port 8800 --no-notify

POST 는 `X-Desk: 1` 헤더가 있어야 받는다 — 다른 사이트가 브라우저를 시켜 이 서버에 요청을 보내는 것(CSRF)을 막는다.
화면 파일은 요청마다 디스크에서 읽어 새로고침만 하면 새것이 나간다. 서버 코드(.py)는 다시 켜야 바뀐다 — 화면에 띠로 알린다.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from memodesk import ai_clients, config, notes, projects, providers, runner, setup

WEB_DIR = config.APP_DIR / "web"
PAGES = {"/": WEB_DIR / "index.html"}
STATIC_FILES = {"common.css": "text/css; charset=utf-8", "common.js": "text/javascript; charset=utf-8"}
MODEL_RE = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,60}$")
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
EFFORT_LABEL = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "Extra high", "max": "Max", "ultra": "Ultra"}


# ── 서버 코드가 바뀌었나 ─────────────────────────────────────────────────────

def code_stamp() -> float:
    files = list((config.APP_DIR / "memodesk").rglob("*.py"))
    return max(f.stat().st_mtime for f in files if f.exists())


STARTED_CODE_STAMP = code_stamp()


def restart_needed() -> bool:
    return code_stamp() > STARTED_CODE_STAMP


# ── 상태 ─────────────────────────────────────────────────────────────────────

def model_state() -> dict:
    """추가한 AI 마다 모델 · 추론 강도. 목록은 그 AI 프로그램이 받아 둔 것(없으면 이름을 직접 적는다)."""
    models = config.load().get("models") or {}
    out = []
    for ai in setup.added():
        info = providers.get(ai)
        picked = models.get(ai) or {}
        out.append({"ai": ai, "name": info["name"], "model": picked.get("model", ""), "effort": picked.get("effort", ""),
                    "models": ai_clients.model_list(ai), "has_effort": ai in ("claude", "codex"), "hint": info.get("model_hint", "")})
    return {"ais": out, "effort_label": EFFORT_LABEL}


def set_models(ai: str, model: str, effort: str) -> None:
    if ai not in setup.added():
        raise ValueError("추가한 AI 가 아니다")
    if model and not MODEL_RE.match(model):
        raise ValueError(f"모델 이름에 쓸 수 없는 글자가 있다: {model}")
    if effort and effort not in EFFORTS:
        raise ValueError(f"모르는 추론 강도: {effort}")
    models = dict(config.load().get("models") or {})
    models[ai] = {"model": model, "effort": effort}
    config.update(models=models)


def project_row(project: dict, others: list[dict]) -> dict:
    pid = project["id"]
    folder = projects.data_dir(pid)
    job = runner.JOBS.get(pid)
    path = Path(project["path"])
    try:
        warning = projects.overlap_warning(path, [o for o in others if o["id"] != pid])
    except ValueError as exc:
        warning = str(exc)
    return {**{k: project.get(k) for k in ("id", "name", "path", "group", "excludes", "instructions")},
            "path_ok": path.is_dir(), "warning": warning,
            "notes": notes.load(folder),
            "job": job.public() if job else None,
            "jobs": [j.public() for j in runner.running_jobs(pid)],
            "paused": runner.is_paused(pid), "pause_after": runner.pause_after_pending(pid),
            "queue_running": pid in runner.RUNNERS,
            "history": runner.read_jsonl(folder / runner.JOBS_NAME)[-5:][::-1],
            "usage": runner.usage_rows(folder)}


def state() -> dict:
    all_projects = projects.all_projects()
    return {"projects": [project_row(p, all_projects) for p in all_projects], "models": model_state(),
            "restart_needed": restart_needed(), "data_dir": str(config.DATA_DIR),
            "ais": setup.check()["ais"]}   # 메모 칸의 AI 버튼(준비된 것만 누를 수 있다) — 점검 결과를 다시 쓴다


def decode_images(body: dict) -> list[tuple[str, bytes]]:
    """화면이 붙여 보낸 그림(`images: [{name, data: data URL}]`) → (이름, 바이트)."""
    try:
        return [(str(i.get("name") or "paste.png"), base64.b64decode(str(i.get("data", "")).split(",", 1)[-1]))
                for i in (body.get("images") or [])]
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"그림을 읽지 못했다: {exc}") from exc


def open_folder(path: Path) -> None:
    """프로젝트 폴더를 탐색기로 연다(이 PC 에서 서버가 연다)."""
    if not path.is_dir():
        raise ValueError(f"없는 폴더다: {path}")
    if os.name == "nt":
        os.startfile(str(path))   # noqa: S606 — 사람이 등록한 프로젝트 경로만 연다
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def attachment(pid: str, note_id: str, name: str) -> Path | None:
    """메모에 붙인 그림. 정해진 폴더 안의 그림 파일만 내준다(요청 값으로 경로를 짓기 전에 모양을 본다)."""
    if not re.fullmatch(rf"{notes.PREFIX}\d+", note_id) or Path(name).name != name \
            or Path(name).suffix.lower() not in notes.ATTACH_SUFFIXES:
        return None
    root = (projects.data_dir(pid) / notes.ATTACH_DIR / note_id).resolve()
    path = (root / name).resolve()
    return path if root in path.parents and path.is_file() else None


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):   # 폴링이 잦아 요청마다 찍지 않는다
        pass

    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in PAGES:
            return self.send(200, PAGES[url.path].read_bytes(), "text/html; charset=utf-8")
        if url.path.startswith("/static/") and url.path[len("/static/"):] in STATIC_FILES:
            name = url.path[len("/static/"):]
            return self.send(200, (WEB_DIR / name).read_bytes(), STATIC_FILES[name])
        if url.path == "/api/state":
            return self.send_json(state())
        if url.path == "/api/setup":
            return self.send_json(setup.check(force=query.get("force") == "1"))
        if url.path == "/api/attachment":
            try:
                path = attachment(query.get("project", ""), query.get("note", ""), query.get("file", ""))
            except ValueError:
                path = None
            if path is None:
                return self.send(404, b"not found", "text/plain")
            return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.headers.get("X-Desk") != "1":
            return self.send_json({"error": "X-Desk 헤더가 없다"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/models":
                set_models(str(body.get("ai", "")), str(body.get("model", "")).strip(), str(body.get("effort", "")).strip())
                return self.send_json({"ok": True, "models": model_state()})
            if path == "/api/pick-folder":
                return self.send_json({"ok": True, "path": setup.pick_folder()})
            if path == "/api/setup/run":
                return self.send_json({"ok": True, **setup.run_action(str(body.get("action", "")), str(body.get("value", "")),
                                                                  str(body.get("name", "")).strip())})
            if path.startswith("/api/projects/"):
                return self.send_json({"ok": True, **self.post_project(path, body)})
            self.post_note(path, body)
            self.send_json({"ok": True})
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)

    def post_project(self, path: str, body: dict) -> dict:
        with runner.LOCK:
            if path == "/api/projects/add":
                project, warning = projects.add(body.get("name", ""), body.get("path", ""), body.get("group", ""),
                                                body.get("excludes", ""), body.get("instructions", ""))
                return {"project": project, "warning": warning}
            pid = str(body.get("project", ""))
            project = projects.get(pid)
            if path == "/api/projects/edit":
                changes = {k: body[k] for k in projects.FIELDS if k in body}
                if "path" in changes and Path(str(changes["path"]).strip().strip('"')).resolve() != Path(project["path"]) \
                        and runner.busy(pid):
                    raise ValueError("작업이 도는 중에는 경로를 바꿀 수 없다 — 끝난 뒤나 멈춘 뒤에")
                updated, warning = projects.edit(pid, changes)
                return {"project": updated, "warning": warning}
            if path == "/api/projects/remove":
                return self.remove_project(pid, bool(body.get("delete_records")))
            if path == "/api/projects/open":
                open_folder(Path(project["path"]))
                return {}
        raise ValueError("없는 경로")

    def remove_project(self, pid: str, delete_records: bool) -> dict:
        """프로젝트 삭제 — MemoDesk 목록에서 빼고 기록은 휴지통(data/trash)으로. 실제 폴더는 건드리지 않는다.
        도는 작업이 있으면 멈추고, 되돌림이 끝날 때까지(최대 60초) 기다린 뒤 지운다 — 되돌림이 기록 폴더의 백업을 쓰기 때문이다.
        LOCK 을 쥔 채 기다리면 작업 마무리(finish)가 LOCK 을 못 얻어 멈추므로, 기다리는 동안은 LOCK 을 놓는다."""
        runner.LOCK.release()
        try:
            if runner.busy(pid):
                runner.stop(pid)
                deadline = time.monotonic() + 60
                while runner.busy(pid) and time.monotonic() < deadline:
                    time.sleep(0.5)
                if runner.busy(pid):
                    raise ValueError("작업이 아직 끝나지 않았습니다 — 잠시 뒤 다시 삭제하세요")
        finally:
            runner.LOCK.acquire()
        moved = projects.remove(pid, keep_records=not delete_records)
        runner.JOBS.pop(pid, None)
        runner.LANES.pop(pid, None)
        return {"moved_records": moved}

    @staticmethod
    def plain_memo(folder: Path, note_id: str) -> None:
        """메모 종류는 없앴다(2026-10-14 '그냥 메모야'). 예전에 '사람' 으로 적은 메모를 다시 맡기면 보통 메모로 돌린다."""
        note = next((n for n in notes.load(folder) if n["id"] == note_id), None)
        if note and notes.kind_of(note) in notes.HUMAN_KINDS:
            notes.set_kind(folder, note_id, "code")

    def post_note(self, path: str, body: dict) -> None:
        pid = str(body.get("project", ""))
        folder = projects.data_dir(pid)   # 목록에 없는 프로젝트면 여기서 거절한다
        note_id = str(body.get("id", ""))
        before = str(body.get("before") or "") or None
        with runner.LOCK:
            if path == "/api/notes":
                ai = str(body.get("ai", ""))
                if ai not in setup.added():
                    raise ValueError("보낼 AI 를 고르세요 — 없으면 왼쪽 [환경 점검]에서 AI 를 추가합니다")
                note = notes.add(folder, str(body.get("text", "")), "code", before, ai=ai)   # 종류 없이 — 그냥 메모
                images = decode_images(body)
                if images:
                    # LOCK 안에서 붙인 뒤에 kick 해야 AI 가 그림 없는 메모를 집지 않는다
                    try:
                        notes.attach(folder, note["id"], images)
                    except ValueError:
                        notes.remove(folder, note["id"])   # 그림이 잘못됐으면 메모도 넣지 않는다
                        raise
                runner.kick(pid)
            elif path == "/api/notes/move":
                notes.move(folder, note_id, before)
                runner.kick(pid)
            elif path == "/api/notes/kind":
                notes.set_kind(folder, note_id, str(body.get("kind", "")))
                runner.kick(pid)
            elif path == "/api/notes/ai":
                ai = str(body.get("ai", ""))
                if ai not in setup.added():
                    raise ValueError("추가한 AI 가 아니다")
                notes.set_ai(folder, note_id, ai)
                runner.kick(pid)
            elif path == "/api/notes/text":
                notes.edit_text(folder, note_id, str(body.get("text", "")))
            elif path == "/api/notes/requeue":
                if notes.is_working(folder, note_id):
                    raise ValueError("처리 중인 메모다")
                self.plain_memo(folder, note_id)
                notes.set_status(folder, [note_id], "queued", "사람이 다시 맡김")
                runner.kick(pid)
            elif path == "/api/notes/refine":
                self.plain_memo(folder, note_id)
                notes.refine(folder, note_id, str(body.get("text", "")), decode_images(body))
                runner.kick(pid)
            elif path == "/api/notes/status":
                if notes.is_working(folder, note_id):
                    raise ValueError("처리 중인 메모는 상태를 바꿀 수 없다 — 먼저 멈춘다")
                status = str(body.get("status"))
                if status not in ("done", "open"):
                    raise ValueError("사람이 바꿀 수 있는 상태는 완료 · 열림뿐이다")
                notes.set_status(folder, [note_id], status, "사람이 상태를 바꿈")
            elif path == "/api/notes/delete":
                notes.remove(folder, note_id)
            elif path == "/api/stop":
                runner.stop(pid)
            elif path == "/api/resume":
                runner.resume(pid)
            elif path == "/api/pause_after":
                runner.pause_after(pid, bool(body.get("on")))
            else:
                raise ValueError("없는 경로")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    saved = config.load()
    parser = argparse.ArgumentParser(description="MemoDesk — 프로젝트별 메모 대기열 · AI 처리")
    parser.add_argument("--port", type=int, default=int(saved.get("port") or config.DEFAULT_PORT))
    parser.add_argument("--no-notify", action="store_true", help="바탕화면 알림을 띄우지 않는다")
    args = parser.parse_args()
    runner.SETTINGS["notify"] = not args.no_notify and bool(saved.get("notify", True))
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for line in runner.recover_interrupted():
        print(line)
    for project in projects.all_projects():
        runner.kick(project["id"])   # 멈춤이 아닌 프로젝트의 남은 대기열을 이어서 처리한다
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"MemoDesk: http://127.0.0.1:{args.port}  · 기록: {config.DATA_DIR}")
    print("끄려면 Ctrl+C (돌던 작업은 끊기고, 다음에 켤 때 되돌린다)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        runner.stop_all()
    return 0
