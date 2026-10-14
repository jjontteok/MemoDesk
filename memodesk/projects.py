"""프로젝트 = 이름 + 경로(+ 묶음 · 백업 제외 목록 · 추가 지시).

- id 는 추가할 때 이름에서 만들고 **바뀌지 않는다** — 기록(`data/projects/{id}/`)이 id 에 묶인다. 경로를 바꿔도 그대로다.
- AI 가 고칠 수 있는 범위는 그 경로 안뿐이다. 같은 경로를 두 번 넣지 않는다. 한 경로가 다른 프로젝트 경로 **안**에 있으면
  막지는 않고 경고한다(같은 파일을 두 대기열이 고칠 수 있다).
- MemoDesk 자신과 기록 폴더는 프로젝트로 넣지 않는다 — AI 가 작업대 코드나 메모 파일을 고치게 된다.
- 지우기는 **목록에서만** 뺀다. 프로젝트 폴더는 건드리지 않고, 기록은 `data/trash/` 로 옮긴다(지우지 않는다).
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from memodesk import config
from memodesk.notes import KST, now

PROJECTS_DIR = config.DATA_DIR / "projects"
TRASH_DIR = config.DATA_DIR / "trash"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# 백업할 때 늘 빼는 폴더 — 크고, AI 가 고칠 일이 없고, 되살리면 오히려 깨진다(.git)
DEFAULT_EXCLUDES = (".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".next", ".cache", ".idea")
FIELDS = ("name", "path", "group", "excludes", "instructions")


def all_projects() -> list[dict]:
    return [p for p in config.load()["projects"] if isinstance(p, dict) and ID_RE.match(str(p.get("id", "")))]


def get(project_id: str) -> dict:
    for project in all_projects():
        if project["id"] == project_id:
            return project
    raise ValueError(f"없는 프로젝트: {project_id}")


def data_dir(project_id: str) -> Path:
    """프로젝트 기록 폴더. id 는 목록에 있는 것만 받는다(요청 값으로 경로를 짓기 전에 반드시 거친다)."""
    get(project_id)
    return PROJECTS_DIR / project_id


def excludes(project: dict) -> list[str]:
    extra = [e.strip().strip("/\\") for e in project.get("excludes") or [] if str(e).strip()]
    return list(dict.fromkeys([*DEFAULT_EXCLUDES, *extra]))


def _slug(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "project"
    if not base[0].isalnum():
        base = "p" + base
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _clean_path(raw: str) -> Path:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("경로를 적어 주세요")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"전체 경로(예: C:\\work\\my-project)로 적어 주세요: {text}")
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"없는 폴더다: {path}")
    for own in (config.APP_DIR, config.DATA_DIR):
        if path == own or own in path.parents or path in own.parents:
            raise ValueError(f"MemoDesk 자신이나 그 기록 폴더는 프로젝트로 넣지 않는다: {path}")
    return path


def _clean_list(value) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[\n,]", value)
    return [str(v).strip() for v in value or [] if str(v).strip()]


def overlap_warning(path: Path, others: list[dict]) -> str:
    for other in others:
        o = Path(other["path"])
        if path == o:
            raise ValueError(f"이미 있는 경로다 — 프로젝트 「{other['name']}」")
        if o in path.parents:
            return f"이 경로는 프로젝트 「{other['name']}」 안에 있습니다 — 두 대기열이 같은 파일을 고칠 수 있습니다"
        if path in o.parents:
            return f"프로젝트 「{other['name']}」 이 이 경로 안에 있습니다 — 두 대기열이 같은 파일을 고칠 수 있습니다"
    return ""


def add(name: str, path: str, group: str = "", excludes_raw="", instructions: str = "") -> tuple[dict, str]:
    name = str(name or "").strip()
    if not name:
        raise ValueError("이름을 적어 주세요")
    clean = _clean_path(path)
    data = config.load()
    projects = [p for p in data["projects"] if isinstance(p, dict)]
    warning = overlap_warning(clean, projects)
    # 목록에서 뺐지만 기록을 남긴 프로젝트의 폴더 이름도 피한다 — 새 프로젝트가 옛 메모를 물려받지 않게
    taken = {p.get("id") for p in projects} | ({d.name for d in PROJECTS_DIR.iterdir()} if PROJECTS_DIR.is_dir() else set())
    project = {"id": _slug(name, taken), "name": name[:60], "path": str(clean),
               "group": str(group or "").strip()[:30], "excludes": _clean_list(excludes_raw),
               "instructions": str(instructions or "").strip(), "created_at": now()}
    projects.append(project)
    config.update(projects=projects)
    (PROJECTS_DIR / project["id"]).mkdir(parents=True, exist_ok=True)
    return project, warning


def edit(project_id: str, changes: dict) -> tuple[dict, str]:
    """이름 · 경로 · 묶음 · 제외 목록 · 추가 지시를 바꾼다. 작업이 도는 중인지는 부르는 쪽(runner)이 본다."""
    data = config.load()
    projects = [p for p in data["projects"] if isinstance(p, dict)]
    target = next((p for p in projects if p.get("id") == project_id), None)
    if target is None:
        raise ValueError(f"없는 프로젝트: {project_id}")
    warning = ""
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name:
            raise ValueError("이름을 적어 주세요")
        target["name"] = name[:60]
    if "path" in changes:
        clean = _clean_path(changes["path"])
        warning = overlap_warning(clean, [p for p in projects if p is not target])
        target["path"] = str(clean)
    if "group" in changes:
        target["group"] = str(changes["group"] or "").strip()[:30]
    if "excludes" in changes:
        target["excludes"] = _clean_list(changes["excludes"])
    if "instructions" in changes:
        target["instructions"] = str(changes["instructions"] or "").strip()
    config.update(projects=projects)
    return target, warning


def remove(project_id: str, keep_records: bool = True) -> str:
    """목록에서 뺀다. 기록은 지우지 않고 `data/trash/{id}-{시각}` 으로 옮긴다(keep_records=False 여도 옮기기만)."""
    data = config.load()
    projects = [p for p in data["projects"] if isinstance(p, dict)]
    if not any(p.get("id") == project_id for p in projects):
        raise ValueError(f"없는 프로젝트: {project_id}")
    config.update(projects=[p for p in projects if p.get("id") != project_id])
    folder = PROJECTS_DIR / project_id
    if keep_records or not folder.exists():
        return ""
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    dest = TRASH_DIR / f"{project_id}-{datetime.now(KST).strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(folder), str(dest))
    return str(dest)
