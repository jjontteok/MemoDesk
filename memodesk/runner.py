"""처리기 — 프로젝트마다 대기열을 위에서부터 AI 에게 맡기고, 작업 전 백업 · 실패와 멈춤 때 되돌림 · 꺼졌다 켜질 때 복구.

차시 작업대(content-pipeline `lesson_desk.py`)에서 교과 전용 부분(빌드 · 화면 검사 · 그림 · 음성)을 빼고 가져왔다.

- **작업** = 처리기가 한 번에 집은 같은 종류 연속 메모 묶음 하나. 작업 번호 = 시각(`20261014-153000`).
- **줄(lane)** = AI 별 실행 줄. 줄마다 한 번에 한 작업. 1차는 클로드 줄 하나.
- **백업** — 작업 전에 프로젝트 폴더를 `data/projects/{id}/backup/{작업}/` 에 복사한다(제외 목록 · 크기 상한).
  상한을 넘으면 작업을 시작하지 않는다. 되돌림은 **그 작업이 바꾼 것만** — 백업과 다른 파일을 백업으로, 작업 중 새로 생긴
  파일은 `orphans/{작업}/` 로 옮긴다(지우지 않는다).
- **처리기는 조용히 죽지 않는다** — 어떤 예외로 빠져도 '도는 중' 표시를 치우고 멈춤 + 알림(차시 작업대 실측 2026-10-08).
- 작업 중에 꺼졌으면 다음에 켤 때 되돌리고 그 프로젝트를 **멈춤**으로 둔다(켜자마자 AI 비용이 나가지 않게).
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from memodesk import config, failures, notes, notify, projects, providers, setup, usage
from memodesk.notes import KST

IS_WINDOWS = os.name == "nt"
JOBS_NAME = "jobs.jsonl"
STATE_NAME = "state.json"           # 프로젝트별 멈춤 · '이번 작업 끝나면 멈춤'
USAGE_KEEP = 10
BACKUP_MAX_BYTES = 500 * 1024 * 1024
# 메모 종류 → (단계 이름, 작업 모듈, 결과 파일)
AI_KIND = {"code": ("AI 처리", "memodesk.agents.fix", "last-fix.json")}
RESULT_LABEL = {"fixed": "고침", "needs_confirm": "확인 필요", "not_fixed": "못 고침"}
DONE_RESULTS = {"fixed"}            # 확인 대기로 보내는 결과 — 파일이 실제로 바뀐 것

JOBS: dict[str, "Job"] = {}                    # 프로젝트 → 지금(또는 마지막) 작업
LANES: dict[str, dict[str, "Job"]] = {}        # 프로젝트 → {줄: 도는 작업}
RUNNERS: set[str] = set()                      # 처리기가 도는 프로젝트
WAKE: dict[str, "queue.Queue"] = {}            # 프로젝트 → 처리기가 기다리는 통(끝난 작업 · 깨우기 None)
SESSIONS: dict[str, dict] = {}                 # 프로젝트 → 이번 대기열 한 바퀴의 집계(끝날 때 알림)
SETTINGS = {"notify": True}
LOCK = threading.RLock()
_STAMP_LOCK = threading.Lock()
_last_stamp = ""


# ── 프로젝트 상태(멈춤) ────────────────────────────────────────────────────────

def project_state(pid: str) -> dict:
    path = projects.data_dir(pid) / STATE_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        return {}


def _save_state(pid: str, data: dict) -> None:
    folder = projects.data_dir(pid)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / STATE_NAME).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_paused(pid: str) -> bool:
    return bool(project_state(pid).get("paused"))


def pause_after_pending(pid: str) -> bool:
    return bool(project_state(pid).get("pause_after"))


def set_paused(pid: str, paused: bool) -> None:
    data = project_state(pid)
    data.pop("pause_after", None)   # 멈췄든 다시 시작했든 '끝나면 멈춤' 예약은 끝났다
    if paused:
        data["paused"] = True
    else:
        data.pop("paused", None)
    _save_state(pid, data)


def set_pause_after(pid: str, on: bool) -> None:
    data = project_state(pid)
    if on:
        data["pause_after"] = True
    else:
        data.pop("pause_after", None)
    _save_state(pid, data)


# ── 작업 ─────────────────────────────────────────────────────────────────────

class Job:
    def __init__(self, pid: str, steps: list[tuple[str, list[str], Path]], stamp: str, note_ids: list[str], note_kind: str):
        self.project = pid
        self.kind = "ai"
        self.steps = steps
        self.stamp = stamp            # 작업 번호 — 로그 · 백업 · 사용량(tag)을 잇는다
        self.note_ids = note_ids
        self.note_kind = note_kind
        self.dir = projects.data_dir(pid)
        self.started = datetime.now(KST)
        self.log_path = self.dir / "jobs" / f"{stamp}-ai.log"
        self.state = "running"
        self.step = ""
        self.summary = ""
        self.results: dict[str, int] = {}
        self.outcomes: dict[str, int] = {}
        self.proc: subprocess.Popen | None = None
        self.stop_requested = False
        self.ended: datetime | None = None
        self.ai = ""                  # 이 작업을 맡은 AI(작업 기록 · 화면에 이름으로)

    def public(self) -> dict:
        return {"id": self.stamp, "kind": self.kind, "note_kind": self.note_kind, "note_ids": self.note_ids, "ai": self.ai,
                "state": self.state, "step": self.step, "summary": self.summary,
                "started": self.started.isoformat(timespec="seconds"),
                "ended": self.ended.isoformat(timespec="seconds") if self.ended else "",
                "log": self.log_path.relative_to(config.DATA_DIR).as_posix(), "tail": tail(self.log_path)}


def new_stamp() -> str:
    """작업 번호. 한 초에 여러 작업이 생겨도 겹치지 않게 뒤에 번호를 붙인다."""
    global _last_stamp
    with _STAMP_LOCK:
        base = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
        stamp, n = base, 1
        while stamp <= _last_stamp:
            stamp = f"{base}-{n}"
            n += 1
        _last_stamp = stamp
        return stamp


def tail(path: Path, lines: int = 40) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def write_log(job: Job, message: str) -> None:
    job.log_path.parent.mkdir(parents=True, exist_ok=True)
    with job.log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n[{datetime.now(KST).strftime('%H:%M:%S')}] {message}\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


# ── 백업 · 되돌림 ────────────────────────────────────────────────────────────

def _excluded(rel_parts: tuple[str, ...], rules: list[str]) -> bool:
    """`node_modules` 처럼 이름만 적은 것은 어느 깊이에서나, `docs/big` 처럼 경로로 적은 것은 그 경로 아래만 뺀다."""
    rel = "/".join(rel_parts)
    for rule in rules:
        rule = rule.replace("\\", "/").strip("/")
        if "/" in rule:
            if rel == rule or rel.startswith(rule + "/"):
                return True
        elif rule in rel_parts:
            return True
    return False


def project_files(root: Path, rules: list[str]) -> list[str]:
    """백업 · 되돌림이 보는 파일 목록(제외 목록 밖). 링크는 따라가지 않는다."""
    out = []
    for current, dirs, files in os.walk(root):
        base = Path(current).relative_to(root).parts
        dirs[:] = [d for d in dirs if not _excluded((*base, d), rules) and not (Path(current) / d).is_symlink()]
        for name in files:
            if not _excluded((*base, name), rules):
                out.append("/".join((*base, name)))
    return sorted(out)


def active_marker(pid: str, lane: str) -> Path:
    """줄마다 따로 두는 '작업 중' 표시 — 켤 때 남아 있으면 끊긴 작업이다."""
    return projects.data_dir(pid) / f"active-job-{lane}.json"


def backup_project(pid: str, stamp: str, kind: str) -> Path:
    """작업 전 상태를 남기고 작업 중 표시를 둔다. 크기가 상한을 넘으면 아무것도 쓰지 않고 거절한다."""
    project = projects.get(pid)
    source = Path(project["path"])
    if not source.is_dir():
        raise ValueError(f"프로젝트 경로가 없다: {source}")
    rules = projects.excludes(project)
    files = project_files(source, rules)
    total = sum((source / rel).stat().st_size for rel in files)
    if total > BACKUP_MAX_BYTES:
        raise ValueError(f"백업할 크기가 상한({BACKUP_MAX_BYTES // 1024 // 1024}MB)을 넘는다 — {total // 1024 // 1024}MB. "
                         "[설정]의 백업 제외 목록에 큰 폴더를 더한다")
    backup = projects.data_dir(pid) / "backup" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for rel in files:
        (backup / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, backup / rel)
    marker = {"project": pid, "dir": str(source), "backup": f"backup/{stamp}", "files": files, "excludes": rules,
              "kind": kind}
    active_marker(pid, notes.LANE[kind]).write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    return backup


def restore_project(pid: str, marker_path: Path) -> list[str]:
    """작업 전으로 되돌린다 — 바뀌었거나 없어진 파일은 백업에서, 작업 중 새로 생긴 파일은 orphans 로(지우지 않는다)."""
    if not marker_path.exists():
        return []
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    folder = projects.data_dir(pid)
    backup = folder / marker["backup"]
    target = Path(marker["dir"])
    restored, shelved = [], []
    for rel in marker["files"]:
        if not (backup / rel).exists():
            continue
        if not (target / rel).exists() or (target / rel).read_bytes() != (backup / rel).read_bytes():
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / rel, target / rel)
            restored.append(rel)
    known = set(marker["files"])
    shelf = folder / "orphans" / Path(marker["backup"]).name
    if target.is_dir():
        for rel in project_files(target, marker.get("excludes") or []):
            if rel in known:
                continue
            (shelf / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target / rel), str(shelf / rel))
            shelved.append(rel)
    marker_path.unlink()
    return restored + [f"(작업 중에 새로 생긴 {rel} 은 {shelf.relative_to(folder).as_posix()} 로 옮김)" for rel in shelved]


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


# ── 작업 실행 ────────────────────────────────────────────────────────────────

def job_env() -> dict:
    # 설치 직후에도 AI 프로그램 · node 를 찾게 기본 설치 자리를 PATH 앞에 붙인 환경(setup.tool_env)
    return dict(setup.tool_env(), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def run_job(job: Job) -> None:
    """작업의 단계를 차례로 돈다. 이 함수를 부른 스레드에서 끝까지 돈다."""
    rc = 0
    try:
        for label, cmd, cwd in job.steps:
            if job.stop_requested:
                break
            job.step = label
            write_log(job, f"▶ {label}: {' '.join(cmd)}")
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
            with job.log_path.open("a", encoding="utf-8") as out:
                job.proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=job_env(),
                                            creationflags=flags)
                rc = job.proc.wait()
            job.results[label] = rc
            write_log(job, f"■ {label} 종료 코드 {rc}")
            if job.stop_requested or rc != 0:
                break
        finish(job, rc)
    except Exception as exc:   # noqa: BLE001 — 작업 스레드가 조용히 죽으면 버튼이 영영 '도는 중'으로 남는다
        write_log(job, f"작업대 오류: {exc!r}")
        finish(job, 1)


def finish(job: Job, rc: int) -> None:
    folder = job.dir
    if job.stop_requested:
        job.state, job.summary = "stopped", "멈춤"
    elif job.step == job.steps[-1][0] and rc == 0:
        job.state = "ok"
    else:
        why = failures.reason_from_log(job.log_path)
        job.summary = f"{job.step} 실패 — {why}" if why else f"{job.step} 실패 (종료 코드 {rc})"
        job.state = "failed"
    with LOCK:
        marker = active_marker(job.project, notes.LANE[job.note_kind])
        if job.state == "ok":
            marker.unlink(missing_ok=True)
            job.summary = apply_ai_result(job)
        else:
            restored = restore_project(job.project, marker)
            write_log(job, f"작업 전으로 되돌림: {', '.join(restored) or '바뀐 것 없음'}")
            if job.state == "stopped":
                notes.release_working(folder, f"멈춤 — 되돌리고 대기로 ({job.stamp})", to="queued", ids=job.note_ids)
            else:
                notes.release_working(folder, f"{job.summary} — 되돌림 ({job.stamp})", ids=job.note_ids)
        if not any(j is not job for j in LANES.get(job.project, {}).values()):
            prune_usage(folder)
    job.ended = datetime.now(KST)
    tally(job)
    if job.state == "failed":
        alert(f"{project_name(job.project)} 작업 실패 — {', '.join(job.note_ids)}", job.summary)
    write_log(job, f"끝 — {job.state} {job.summary}")
    record = {k: v for k, v in job.public().items() if k != "tail"}
    with (folder / JOBS_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def short_line(text: str, limit: int = 60) -> str:
    """긴 설명에서 카드에 보일 한 줄 — 첫 줄의 첫 문장을 limit 자로."""
    first = text.strip().lstrip("- ").splitlines()[0] if text.strip() else ""
    first = first.split(". ")[0]
    return first if len(first) <= limit else first[:limit].rstrip() + "…"


def apply_ai_result(job: Job) -> str:
    """결과 파일대로 이 작업이 맡은 메모의 상태를 바꾼다. 된 것만 '확인 대기', 나머지는 이유를 달고 '열림'."""
    folder = job.dir
    label, _, result_name = AI_KIND[job.note_kind]
    result_path = folder / result_name
    items = json.loads(result_path.read_text(encoding="utf-8")).get("notes", []) if result_path.exists() else []
    pending = list(job.note_ids)
    counts: dict[str, int] = {}
    for item in items:
        if item.get("id") not in pending:
            continue
        pending.remove(item["id"])
        outcome = str(item.get("result", ""))
        counts[outcome] = counts.get(outcome, 0) + 1
        detail = str(item.get("detail") or "").strip()
        headline = str(item.get("headline") or "").strip() or short_line(detail)
        result = {"kind": outcome, "label": RESULT_LABEL.get(outcome, outcome), "step": label, "headline": headline,
                  "detail": detail, "files": [str(f) for f in item.get("files") or []], "job": job.stamp}
        notes.set_result(folder, item["id"], "review" if outcome in DONE_RESULTS else "open", result,
                         f"{label} — {RESULT_LABEL.get(outcome, outcome)}: {headline}")
    if pending:
        notes.set_status(folder, pending, "open", f"{label} — AI 가 이 메모의 결과를 안 적었다")
        counts["missing"] = len(pending)
    job.outcomes = counts
    parts = [f"{RESULT_LABEL.get(k, k)} {v}건" for k, v in counts.items() if k != "missing"] \
        + ([f"결과 없음 {len(pending)}건"] if pending else [])
    return " · ".join(parts)


def model_args(ai: str) -> list[str]:
    picked = (config.load().get("models") or {}).get(ai) or {}
    return ((["--model", picked["model"]] if picked.get("model") else [])
            + (["--effort", picked["effort"]] if picked.get("effort") else []))


def ai_job(pid: str, group: list[dict]) -> Job:
    """대기열 맨 앞 묶음으로 작업 하나를 만든다(백업을 뜨고 메모를 '처리 중'으로)."""
    folder = projects.data_dir(pid)
    stamp = new_stamp()
    kind = notes.kind_of(group[0])
    ids = [n["id"] for n in group]
    label, module, result_name = AI_KIND[kind]
    ai = group[0].get("ai") or (setup.added()[0] if setup.added() else "")   # 예전 메모(AI 없음)는 첫 번째로 추가한 AI
    if not ai:
        raise ValueError("이 메모를 보낼 AI 가 없다 — 왼쪽 [환경 점검]에서 AI 를 추가한 뒤 [다시 맡기기]")
    if ai not in providers.PROVIDERS:
        raise ValueError(f"모르는 AI: {ai}")
    cli = providers.find_cli(ai)
    if not cli:
        raise ValueError(f"AI 프로그램({providers.get(ai)['cli_name']})이 설치되어 있지 않다 — 왼쪽 [환경 점검]에서 설치한 뒤 [다시 맡기기]")
    (folder / result_name).unlink(missing_ok=True)   # 지난 작업의 결과를 이번 것으로 읽지 않게
    backup_project(pid, stamp, kind)
    try:
        notes.set_status(folder, ids, "working", f"{label} 시작 ({stamp})")
    except Exception:
        active_marker(pid, notes.LANE[kind]).unlink(missing_ok=True)   # 아무것도 안 바꿨다
        raise
    cmd = [sys.executable, "-B", "-m", module, "--project", pid, "--stamp", stamp, "--provider", ai, "--cli", cli, *model_args(ai)]
    job = Job(pid, [(label, cmd, config.APP_DIR)], stamp, ids, kind)
    job.ai = ai
    write_log(job, f"{project_name(pid)} · {label} · 메모 {', '.join(ids)}")
    return job


# ── 대기열 처리기 ─────────────────────────────────────────────────────────────

def run_queue(pid: str) -> None:
    """처리기 — 어떤 이유로든 빠져나가면 '도는 중' 표시를 치운다. 남기면 kick 이 처리기가 돈다고 보고 다시 안 띄운다."""
    try:
        _run_queue(pid)
    except Exception as exc:   # noqa: BLE001
        print(f"  {pid}: 처리기 오류로 멈춤 — {exc!r}", flush=True)
        alert(f"{project_name(pid)} 처리기 오류", f"{type(exc).__name__}: {exc} — 대기열을 멈췄다. [다시 시작]으로 이어 간다")
        with LOCK:
            try:
                set_paused(pid, True)
            except Exception:   # noqa: BLE001 — 프로젝트가 지워진 뒤면 상태 파일도 없다
                pass
    finally:
        with LOCK:
            RUNNERS.discard(pid)
            WAKE.pop(pid, None)


def _run_queue(pid: str) -> None:
    """대기열이 빌 때까지(또는 멈출 때까지) 처리한다. 작업 하나가 끝날 때마다 대기열을 다시 읽는다."""
    folder = projects.data_dir(pid)
    lanes = LANES.setdefault(pid, {})
    finished: queue.Queue[Job | None] = queue.Queue()
    with LOCK:
        WAKE[pid] = finished

    def lane_worker(job: Job) -> None:
        try:
            run_job(job)
        finally:
            finished.put(job)

    while True:
        with LOCK:
            paused = is_paused(pid)
            soft = pause_after_pending(pid)
            while not paused and not soft:
                groups = notes.runnable_groups(notes.load(folder), set(lanes))
                if not groups:
                    break
                lane, group = groups[0]
                try:
                    job = ai_job(pid, group)
                except Exception as exc:   # noqa: BLE001 — 이 묶음만 '시작 못 함' 으로 열고 다음으로(같은 실패를 되풀이하지 않게)
                    reason = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"
                    try:
                        notes.set_status(folder, [n["id"] for n in group], "open", f"시작 못 함: {reason}")
                    except Exception as again:   # noqa: BLE001 — 메모 파일도 못 쓰면 대기열을 세운다
                        print(f"  {pid}: 시작 못 한 묶음을 열림으로도 못 바꿈({again!r}) — 멈춤", flush=True)
                        set_paused(pid, True)
                        break
                    continue
                lanes[lane] = job
                JOBS[pid] = job
                threading.Thread(target=lane_worker, args=(job,), daemon=True).start()
            if not lanes:
                RUNNERS.discard(pid)
                WAKE.pop(pid, None)
                if soft and not paused:
                    set_paused(pid, True)
                    alert_queue_done(pid, title="멈춤")
                elif not paused:
                    alert_queue_done(pid)
                return
        job = finished.get()
        if job is None:
            continue   # 한 줄이 도는 중에 메모가 들어왔거나 바뀌었다 — 쉬는 줄에 줄 것이 생겼는지 다시 본다
        with LOCK:
            lanes.pop(notes.LANE[job.note_kind], None)


def kick(pid: str) -> None:
    """대기열에 할 일이 있고 멈춤이 아니고 아무것도 안 돌면 처리기를 띄운다. 돌고 있으면 깨워서 다시 보게 한다."""
    with LOCK:
        if pid in RUNNERS:
            if pid in WAKE:
                WAKE[pid].put(None)
            return
        if is_paused(pid):
            return
        if pause_after_pending(pid):   # 끝낼 작업 없이 예약만 남았다 — 그냥 멈춘다
            set_paused(pid, True)
            return
        if not notes.has_queued(notes.load(projects.data_dir(pid))):
            return
        RUNNERS.add(pid)
    threading.Thread(target=run_queue, args=(pid,), daemon=True).start()


def running_jobs(pid: str) -> list[Job]:
    with LOCK:
        jobs = [JOBS.get(pid), *LANES.get(pid, {}).values()]
    unique = {id(j): j for j in jobs if j and j.state == "running"}
    return sorted(unique.values(), key=lambda j: j.stamp)


def busy(pid: str) -> bool:
    return pid in RUNNERS or bool(running_jobs(pid))


def stop(pid: str) -> None:
    """대기열을 멈추고, 도는 작업이 있으면 끊는다(finish 가 되돌리고 메모를 대기로 돌린다)."""
    set_paused(pid, True)
    for job in running_jobs(pid):
        job.stop_requested = True
        write_log(job, "멈춤 요청")
        if job.proc:
            kill_tree(job.proc)


def resume(pid: str) -> None:
    set_paused(pid, False)
    kick(pid)


def pause_after(pid: str, on: bool) -> None:
    """[이번 작업 끝나면 멈춤] — 도는 작업은 끝까지 마치게 두고 다음 메모로 넘어가지 않는다. 도는 게 없으면 바로 멈춘다."""
    if not on:
        set_pause_after(pid, False)
    elif busy(pid):
        set_pause_after(pid, True)
    else:
        set_paused(pid, True)


def recover_interrupted() -> list[str]:
    """작업대가 작업 중에 꺼졌으면 — 작업 전으로 되돌리고, 메모는 대기로, 그 프로젝트는 멈춤으로 둔다."""
    lines = []
    for project in projects.all_projects():
        folder = projects.data_dir(project["id"])
        markers = sorted(folder.glob("active-job-*.json")) if folder.is_dir() else []
        if not markers:
            continue
        restored = [f for marker in markers for f in restore_project(project["id"], marker)]
        notes.release_working(folder, "작업대가 작업 중에 꺼짐 — 되돌리고 대기로", to="queued")
        set_paused(project["id"], True)
        lines.append(f"  {project['name']}: 끊긴 작업 {len(markers)}개를 되돌림({', '.join(restored) or '바뀐 것 없음'}) — 대기열은 멈춰 둠")
    return lines


# ── 알림 · 사용량 ─────────────────────────────────────────────────────────────

def project_name(pid: str) -> str:
    try:
        return projects.get(pid)["name"]
    except ValueError:
        return pid


def alert(title: str, body: str) -> None:
    """바탕화면 알림. 기다리지 않는다 — PowerShell 이 느려도 작업을 붙잡지 않게 따로 띄운다."""
    if not SETTINGS.get("notify"):
        return
    threading.Thread(target=notify.toast, args=(f"MemoDesk · {title}", body), daemon=True).start()


def tally(job: Job) -> None:
    session = SESSIONS.setdefault(job.project, {"done": 0, "open": 0, "failed": 0, "jobs": 0})
    if job.state == "stopped":
        return
    session["jobs"] += 1
    if job.state == "failed":
        session["failed"] += len(job.note_ids)
        return
    for outcome, count in job.outcomes.items():
        session["done" if outcome in DONE_RESULTS else "open"] += count


def alert_queue_done(pid: str, title: str = "대기열 완료") -> None:
    session = SESSIONS.pop(pid, None)
    if not session or not session["jobs"]:
        return
    parts = [f"고침 {session['done']}"] + ([f"못 한 것 {session['open']}"] if session["open"] else []) \
        + ([f"실패 {session['failed']}"] if session["failed"] else [])
    tail_text = " · 남은 메모는 [다시 시작]으로 이어서" if title == "멈춤" else ""
    alert(f"{project_name(pid)} {title}", " · ".join(parts) + tail_text)


def prune_usage(folder: Path) -> None:
    """사용량을 최근 USAGE_KEEP 개 작업만 남긴다."""
    path = folder / usage.LOG_NAME
    rows = read_jsonl(path)
    tags: list[str] = []
    for row in rows:
        tag = row.get("tag")
        if tag and tag not in tags:
            tags.append(tag)
    keep = set(tags[-USAGE_KEEP:])
    kept = [row for row in rows if row.get("tag") in keep]
    if len(kept) != len(rows):
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")


def usage_rows(folder: Path) -> list[dict]:
    """작업별 사용량(최근 것이 위). 작업 기록(jobs.jsonl)과 작업 번호로 잇는다."""
    jobs = {j.get("id"): j for j in read_jsonl(folder / JOBS_NAME) if j.get("id")}
    by_tag: dict[str, dict] = {}
    for row in read_jsonl(folder / usage.LOG_NAME):
        tag = row.get("tag")
        if not tag or row.get("kind") != "llm":
            continue
        entry = by_tag.setdefault(tag, {"id": tag, "provider": row.get("provider"), "model": row.get("model"),
                                        "input": 0, "cached": 0, "output": 0, "cost_usd": None, "seconds": 0.0, "calls": 0})
        entry["calls"] += 1
        entry["seconds"] += float(row.get("seconds") or 0)
        for key in ("input", "cached", "output"):
            entry[key] += int(row.get(key) or 0)
        if row.get("cost_usd") is not None:
            entry["cost_usd"] = (entry["cost_usd"] or 0) + float(row["cost_usd"])
    out = []
    for tag, entry in by_tag.items():
        job = jobs.get(tag, {})
        entry.update({"note_kind": job.get("note_kind", ""), "note_ids": job.get("note_ids", []),
                      "state": job.get("state", "running"), "started": job.get("started", "")})
        entry["seconds"] = round(entry["seconds"], 1)
        out.append(entry)
    return sorted(out, key=lambda e: e["id"], reverse=True)[:USAGE_KEEP]


def stop_all() -> None:
    """서버를 끌 때 — 도는 작업을 끊는다(되돌림은 다음에 켤 때 recover_interrupted 가 한다)."""
    for pid in list(JOBS):
        for job in running_jobs(pid):
            job.stop_requested = True
            if job.proc:
                kill_tree(job.proc)
