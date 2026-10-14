# MemoDesk

**한국어** · [English](#english)

프로젝트(폴더)마다 **메모 대기열**을 두고, AI(Claude Code)가 위에서부터 차례로 처리하는 로컬 작업대입니다.
결과를 보며 할 일을 적어 두기만 하면, AI 가 그 폴더 안에서 고치고 사람은 결과를 확인해 닫습니다.

```text
[+ 프로젝트 추가] 이름 · 경로
      ↓
메모 적기(화면 캡처 붙여 넣기 가능) ─▶ 대기열
      ↓
작업 전 백업 → 클로드가 그 경로 안의 파일을 고침
      ↓
성공: '확인 대기' + 한 줄 요약      실패 · 멈춤: 그 작업이 바꾼 것만 되돌리고 '열림'
      ↓
사람: 결과를 보고 [완료] / [보완해서 다시 맡기기]
```

## 필요한 것

| 무엇 | 필요 | 비고 |
|---|---|---|
| Windows 10/11 | — | 알림 · 켜기 파일 · 설치 버튼이 Windows 기준입니다. 서버 자체는 macOS · Linux 에서도 돕니다 |
| 파이썬 3.10 이상 | 필수 | 추가 패키지 없음(표준 라이브러리만). `Setup.bat` 이 없으면 설치합니다 |
| 쓸 AI (하나 이상) | 필수 | 환경 점검 창에서 추가합니다(여러 개 가능) — **Claude**(Anthropic) · **ChatGPT Codex**(OpenAI) · **GitHub Copilot** · **Cursor** · **Gemini**(Google) |
| 그 AI 의 프로그램(CLI) | 필수 | [설치하기] 버튼 — Claude · Codex 는 공식 설치 스크립트, Gemini 는 npm(Node.js 20+ 도 버튼으로 설치) |
| 그 AI 의 계정 | 필수 | Claude: Pro · Max · Team · Enterprise / Codex: ChatGPT Plus · Pro · Business · Edu · Enterprise / Gemini: Google 계정(무료, 하루 1,000회). [로그인하기] 버튼 |
| Git for Windows | 권장(Claude) | 없으면 Claude 가 PowerShell 로 명령을 돌려 '지울 파일 보관 폴더로 옮기기'가 막힐 수 있습니다. [설치하기]는 winget, 없으면 GitHub 공식 설치 파일(관리자 확인 창이 뜰 수 있음) |

## 처음 설치

1. 이 레포를 받습니다(`git clone https://github.com/jjontteok/MemoDesk.git` 또는 GitHub 의 **Code → Download ZIP** 후 압축 풀기).
2. **`Setup.bat`** 을 더블클릭합니다. 파이썬이 없으면 설치한 뒤(winget, 없으면 python.org 공식 설치 파일) MemoDesk 를 켭니다.
3. 브라우저에 **환경 점검** 창이 뜹니다. 꼭 필요한 항목이 다 될 때까지 닫히지 않습니다. 강조된 **파란 버튼**을 차례로 누르세요 —
   **쓸 AI 추가하기**(여러 개 가능) → AI 마다 프로그램 [설치하기] → 계정 [로그인하기] → (Claude 는 있으면 좋음) Git [설치하기]. 설치 · 로그인은 새 창에서 진행되고, 끝나면 창이 저절로 ✔ 로 바뀝니다.
   하나만 준비돼도 쓸 수 있습니다. AI 는 나중에 왼쪽 [환경 점검] → [AI 추가 · 빼기]로 더하거나 뺍니다.
4. 모두 ✔ 이면 [AI 한 번 불러 보기]로 확인하고(Haiku 한 번, 약 $0.01) [시작하기].
5. 프로젝트를 추가할 때 경로는 **[폴더 고르기]** 로 고르면 됩니다.

다음부터는 **`MemoDesk.bat`** 을 더블클릭합니다(이미 켜져 있으면 브라우저만 엽니다). 직접 켜려면:

```bash
python -B -m memodesk            # http://127.0.0.1:8791
```
검은 서버 창을 닫으면 꺼집니다. 돌던 작업은 다음에 켤 때 되돌리고 그 프로젝트를 멈춤으로 둡니다.

```bash
python -B -m memodesk --port 8800 --no-notify
```

### AI 계정 바꾸기

[환경 점검] → AI 마다 **쓸 계정** 목록에서 고릅니다(다음 작업부터). [새 계정 추가]는 MemoDesk 전용 계정 폴더
(`data/accounts/<AI>/<이름>/`)를 만들고 그 폴더에 로그인합니다 — **이 PC 의 다른 프로그램(터미널의 Claude Code 등) 계정은 바뀌지 않습니다**.
Claude(`CLAUDE_CONFIG_DIR`) · Codex(`CODEX_HOME`) · Gemini(`GEMINI_CLI_HOME`) 가 됩니다. Copilot · Cursor 는 PC 에 계정이 하나라
[다시 로그인]으로 바꾸고, 그러면 그 PC 의 그 AI 계정이 같이 바뀝니다. [목록에서 빼기]는 폴더를 지우지 않고 `data/accounts/removed/` 로 옮깁니다.

## 쓰는 법

1. 왼쪽 **[+ 프로젝트 추가]** — 이름, AI 가 고칠 폴더의 **전체 경로**, 묶음(선택)을 적습니다.
   - 백업에서 뺄 폴더 · AI 에게 줄 추가 지시도 적을 수 있습니다. 폴더의 `CLAUDE.md` · `AGENTS.md` 는 AI 가 알아서 읽습니다.
2. 프로젝트 카드에서 **보낼 AI** 를 고르고 메모를 적은 뒤 **Enter**(줄바꿈은 Shift+Enter). 화면 캡처는 **Ctrl+V** 로 붙입니다.
   - 고른 AI 는 프로젝트마다 기억합니다. 대기 중인 메모도 [AI: …] 칸에서 다른 AI 로 바꿀 수 있습니다.
   - 한 프로젝트에서는 AI 가 달라도 차례대로 하나씩 처리합니다(같은 폴더를 두 AI 가 동시에 고치지 않게).
   - 고쳐 달라는 부탁도, 의견 · 제안을 묻는 질문도 그냥 메모로 적습니다. 답은 서식대로 보이고 [크게 보기]로 읽습니다.
3. 대기열은 위에서부터 처리됩니다. 대기 중인 메모는 끌어서 순서를 바꾸고, 글을 고칠 수 있습니다.
4. 끝난 메모는 **확인 대기**(한 것) 또는 **열림**(못 한 것 — 이유가 붙음)이 됩니다. 결과를 확인하고 **[완료]**.
   - 조금 다르면 **[보완해서 다시 맡기기]** — 지난 결과와 보완 메모를 함께 넘깁니다.
5. **[이번 작업 끝나면 멈춤]** 은 도는 작업을 마치고 멈추고, **[지금 멈춤]** 은 바로 끊고 그 작업을 되돌립니다.

## 안전장치

| 무엇 | 어떻게 |
|---|---|
| 작업 전 백업 | 프로젝트 폴더를 `data/projects/{id}/backup/{작업}/` 에 복사. `.git` · `node_modules` · `dist` · `build` 등은 뺍니다. 500MB 를 넘으면 시작하지 않습니다 |
| 실패 · 멈춤 | **그 작업이 바꾼 것만** 되돌립니다. 작업 중 새로 생긴 파일은 `orphans/` 로 옮깁니다(지우지 않음) |
| 파일 지우기 | 지울 파일은 `removed/{작업}/` 으로 옮기게 합니다. Claude 는 `rm` · `del` · `git` 을 아예 막고, Codex 는 폴더 밖에 못 쓰는 보호 모드, Gemini 는 파일 고치기만 자동 승인으로 돕니다 |
| 경로 밖 | AI 가 고칠 수 있는 곳은 프로젝트 경로뿐입니다. git 레포 안이면 경로 밖이 바뀌었는지 확인해 ⚠ 로 알립니다 |
| 사용자 설정 | Claude 는 `--setting-sources project` 로 돌아 PC 의 전역 허용 규칙을 물려받지 않습니다 |
| 다른 사이트의 요청 | 서버는 `127.0.0.1` 에서만 듣고, POST 는 `X-Desk` 헤더가 있어야 받습니다 |

⚠ **작업이 도는 동안 같은 폴더를 손으로 고치지 마세요.** 실패 · 멈춤 되돌림이 그 수정까지 되돌립니다.
⚠ 커밋 · 푸시 · 배포는 사람이 합니다.

## 기록

모든 기록은 `data/` 에 남고 git 에 올라가지 않습니다(`.gitignore`). 프로젝트 폴더에는 아무것도 쓰지 않습니다.

```text
data/config.json                      포트 · 모델 · 프로젝트 목록 · 쓰는 계정
data/accounts/{AI}/{이름}/              MemoDesk 전용 AI 계정(로그인 정보 — 남에게 주지 마세요)
data/projects/{id}/notes.json         메모
data/projects/{id}/jobs/ · jobs.jsonl 작업 로그 · 이력
data/projects/{id}/backup/            작업 전 백업
data/projects/{id}/removed/ · orphans/ AI 가 치운 파일 · 되돌릴 때 새로 생긴 파일
data/projects/{id}/usage-log.jsonl    토큰 · 비용 · 시간(최근 10개 작업)
```

## 개발

```bash
python -B -m unittest discover -s tests
```

설계와 로드맵은 [docs/설계.md](docs/설계.md). 2차: 코덱스 그림 · 검증 메모, 프로젝트별 빌드 · 검사 명령, git 백업.

---

<a id="english"></a>

# MemoDesk (English)

A local workbench that keeps a **memo queue per project (folder)** and has an AI agent (Claude Code) work through it from the top.
Write down what you want changed while reviewing your work; the AI edits files inside that folder, and you review and close each memo.

```text
[+ Add project] name · path
      ↓
Write a memo (paste screenshots) ─▶ queue
      ↓
Back up the folder → Claude edits files inside that path
      ↓
Success: "Review" + one-line summary     Failure / stop: roll back only this job's changes, mark "Open"
      ↓
You: check the result → [Done] / [Refine and retry]
```

## Requirements

| What | Needed | Notes |
|---|---|---|
| Windows 10/11 | — | Notifications, launcher and install buttons are Windows-first; the server itself runs on macOS/Linux |
| Python 3.10+ | Required | No third-party packages. `Setup.bat` installs it if missing |
| One or more AIs | Required | Add in the setup dialog (several allowed) — **Claude** (Anthropic), **ChatGPT Codex** (OpenAI), **GitHub Copilot**, **Cursor** or **Gemini** (Google) |
| That AI's CLI | Required | [Install] button — official install scripts for Claude/Codex; npm for Gemini (Node.js 20+ is also installed by a button) |
| That AI's account | Required | Claude: Pro/Max/Team/Enterprise · Codex: ChatGPT Plus/Pro/Business/Edu/Enterprise · Gemini: Google account (free, 1,000 requests/day). [Log in] button |
| Git for Windows | Recommended | Without it Claude runs commands through PowerShell and "move files to the removed folder" may be blocked |

## First-time setup

1. Get this repo (`git clone https://github.com/jjontteok/MemoDesk.git`, or **Code → Download ZIP** on GitHub and unzip).
2. Double-click **`Setup.bat`**. It installs Python if needed (winget, or the official python.org installer when winget is missing), then starts MemoDesk.
3. An **환경 점검 (Environment check)** dialog opens and cannot be closed until the required items are ready. Press the highlighted blue buttons in order —
   add one or more AIs → for each, install its program → log in → (optional, Claude) install Git. One ready AI is enough; add or remove AIs later from [환경 점검 / Environment check]. Installs and login run in a new window; the dialog turns ✔ by itself when they finish.
4. When everything is ✔, press [AI 한 번 불러 보기 / Try the AI once] (one Haiku call, about $0.01), then [시작하기 / Start].
5. When adding a project, use **[폴더 고르기 / Pick folder]** instead of typing the path.

Afterwards, double-click **`MemoDesk.bat`** (if it is already running, it just opens the browser), or run:

```bash
python -B -m memodesk            # http://127.0.0.1:8791
```
Closing the server window stops it; an interrupted job is rolled back on the next start and that project is paused.

### Switching AI accounts

In [환경 점검 / Environment check], pick an account from each AI's **account** list (applies from the next job). [새 계정 추가 / Add account]
creates a MemoDesk-only account folder (`data/accounts/<AI>/<name>/`) and logs in there — **other programs on this PC keep their accounts**.
Supported for Claude (`CLAUDE_CONFIG_DIR`), Codex (`CODEX_HOME`) and Gemini (`GEMINI_CLI_HOME`). Copilot and Cursor keep one login per PC,
so switching means logging in again, which changes that AI's account for the whole PC. Removing an account moves its folder to `data/accounts/removed/` instead of deleting it.

## How to use

1. **[+ 프로젝트 추가]** (Add project) — a name, the **absolute path** of the folder the AI may edit, and an optional group.
   - Optional: folders to exclude from backups, and extra instructions. The AI reads the folder's `CLAUDE.md` / `AGENTS.md` by itself.
2. On the project card pick **which AI to send to**, type the memo and press **Enter** (Shift+Enter for a new line). Paste screenshots with **Ctrl+V**.
   - The choice is remembered per project; a queued memo can be moved to another AI. Within a project, memos run one at a time even across AIs.
   - Requests and questions are both just memos. Answers are rendered as formatted text; use [크게 보기 / Read] for a large view.
3. The queue runs top-down. Drag queued memos to reorder, or edit their text before they start.
4. Finished memos become **확인 대기 / Review** (done) or **열림 / Open** (not done, with a reason). Check and press **[완료 / Done]**.
   - Not quite right? **[보완해서 다시 맡기기 / Refine and retry]** sends the previous result together with your follow-up.
5. **[이번 작업 끝나면 멈춤]** pauses after the running job finishes; **[지금 멈춤]** stops immediately and rolls that job back.

## Safety

| What | How |
|---|---|
| Backup before each job | Copies the project to `data/projects/{id}/backup/{job}/`, excluding `.git`, `node_modules`, `dist`, `build`, etc. Refuses to start above 500 MB |
| Failure / stop | Rolls back **only this job's changes**. Files created during the job are moved to `orphans/` (never deleted) |
| Deleting files | The AI cannot run `rm`, `del` or `git`. Files to delete are moved to `removed/{job}/` |
| Outside the path | The AI may only edit inside the project path. Inside a git repo, changes outside the path are reported with ⚠ |
| User settings | Claude runs with `--setting-sources project`, so global allow-rules on the PC are not inherited |
| Cross-site requests | The server listens on `127.0.0.1` only and accepts POST only with the `X-Desk` header |

⚠ **Do not edit the same folder by hand while a job is running** — a rollback would undo your edits too.
⚠ Commits, pushes and deployments are left to you.

## Data

Everything is stored under `data/` (git-ignored). Nothing is written into your project folders.

## Development

```bash
python -B -m unittest discover -s tests
```

Design and roadmap: [docs/설계.md](docs/설계.md) (Korean). Next: Codex lane for image/verify memos, per-project build/check commands, git-based backups.

## License

[MIT](LICENSE)
