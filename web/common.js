// MemoDesk 공통 — 글자 처리 · 토큰 단위 · 요청 · 다시 켜기 띠 · AI 모델 고르기 (차시 작업대 desk_common.js 에서)
// 페이지 스크립트보다 먼저, #models 가 생긴 뒤에 싣는다.

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function time(s) { return s ? s.slice(5, 16).replace("T", " ") : ""; }
// 토큰은 단위로 줄여 소수 첫째 자리까지 — 1a = 1토큰, 1b = 1,000a, 1c = 1,000b
function tok(n) {
  if (n == null) return "-";
  const units = ["a", "b", "c", "d", "e"];
  let v = Number(n), i = 0;
  while (Math.abs(v) >= 1000 && i < units.length - 1) { v /= 1000; i++; }
  if (Number(v.toFixed(1)) >= 1000 && i < units.length - 1) { v /= 1000; i++; }
  return v.toFixed(1) + units[i];
}
async function postJson(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Desk": "1" }, body: JSON.stringify(body) });
  return { res, data: await res.json().catch(() => ({})) };
}

// 서버 코드가 켠 뒤에 바뀌었으면 맨 위에 띠 — 화면만 새것이고 서버는 예전 것이면 화면이 깨진다
function showRestartBanner(on) {
  let bar = document.getElementById("restart-banner");
  if (!on) { if (bar) { bar.remove(); stickyOffsets(); } return; }
  if (bar) return;
  bar = document.createElement("div");
  bar.id = "restart-banner";
  bar.className = "restart-banner";
  bar.textContent = "MemoDesk 코드가 바뀌었습니다 — 서버 창을 닫고 다시 켜면 새 코드로 돕니다(도는 작업이 있으면 끝난 뒤에).";
  document.body.prepend(bar);
  stickyOffsets();
}
// 위에 붙는 것들의 높이 — 다시 켜기 띠(있을 때) → 위 띠 → 사이드바 순으로 겹치지 않게 쌓는다
function stickyOffsets() {
  const root = document.documentElement.style;
  const bar = document.getElementById("restart-banner");
  const nav = document.querySelector(".topnav");
  root.setProperty("--banner-h", `${bar ? bar.offsetHeight : 0}px`);
  root.setProperty("--nav-h", `${nav ? nav.offsetHeight : 0}px`);
}
stickyOffsets();
if (window.ResizeObserver) {
  const watch = new ResizeObserver(stickyOffsets);
  const nav = document.querySelector(".topnav");
  if (nav) watch.observe(nav);
  new MutationObserver(() => { const bar = document.getElementById("restart-banner"); if (bar) watch.observe(bar); stickyOffsets(); })
    .observe(document.body, { childList: true });
}

// ── AI 모델 · 추론 강도(사이드바 아래) — 다음 작업부터 적용. 목록은 Claude Code 가 받아 둔 것을 서버가 읽어 준다 ──
document.getElementById("models").innerHTML = `
  <details id="m-fold">
    <summary><span class="mtitle">AI 모델</span><span class="mpicked" id="m-picked"></span></summary>
    <div class="mbody">
    <label>클로드 <span class="mnote">코드 메모</span><select id="m-claude"></select></label>
    <input id="m-claude-custom" class="hidden" placeholder="클로드 모델 이름 (Enter 로 저장)" spellcheck="false">
    <label>추론 강도<select id="m-claude-effort"></select></label>
    <p class="mnote">다음 작업부터 적용 · 도는 작업은 그대로</p>
    <span class="mmsg" id="m-msg"></span>
    </div>
  </details>`;
{
  const fold = document.getElementById("m-fold");
  try { fold.open = localStorage.getItem("memodesk.models.open") === "1"; } catch { /* 저장소를 못 쓰면 접힌 채로 */ }
  fold.addEventListener("toggle", () => { try { localStorage.setItem("memodesk.models.open", fold.open ? "1" : "0"); } catch { /* 무시 */ } });
}
let modelState = null;
const effortName = e => (modelState && modelState.effort_label[e]) || e;
const modelInfo = id => (modelState?.claude_models || []).find(x => x.id === id) || null;
function renderModels(m) {
  if (!m) return;
  modelState = m;
  const sel = document.getElementById("m-claude"), custom = document.getElementById("m-claude-custom");
  const effortSel = document.getElementById("m-claude-effort");
  if (![sel, custom, effortSel].includes(document.activeElement)) {   // 고르는 중인 칸은 새로고침이 덮지 않는다
    const list = m.claude_models, known = list.some(x => x.id === m.claude);
    const opt = x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`;
    const main = list.filter(x => x.main), rest = list.filter(x => !x.main);
    const html = `<option value="">기본 (CLI 설정)</option>`
      + (rest.length ? `<optgroup label="주 모델">${main.map(opt).join("")}</optgroup><optgroup label="그 밖의 버전">${rest.map(opt).join("")}</optgroup>` : main.map(opt).join(""))
      + `<option value="__custom__">직접 입력…</option>`;
    if (sel.dataset.sig !== html) { sel.innerHTML = html; sel.dataset.sig = html; }
    sel.value = m.claude && !known ? "__custom__" : m.claude;
    custom.classList.toggle("hidden", !(m.claude && !known));
    if (m.claude && !known) custom.value = m.claude;
    const info = modelInfo(m.claude);
    const efforts = info ? info.efforts : ["low", "medium", "high", "xhigh", "max"];
    const first = info && info.recommended ? `기본 (추천: ${effortName(info.recommended)})` : "기본";
    const eh = efforts.length ? `<option value="">${esc(first)}</option>` + efforts.map(e => `<option value="${e}">${esc(effortName(e))}</option>`).join("")
                              : `<option value="">이 모델은 추론 강도가 없습니다</option>`;
    if (effortSel.dataset.sig !== eh) { effortSel.innerHTML = eh; effortSel.dataset.sig = eh; }
    effortSel.disabled = !efforts.length;
    effortSel.value = efforts.includes(m.claude_effort) ? m.claude_effort : "";
  }
  const info = modelInfo(m.claude);
  const line = document.getElementById("m-picked");
  line.textContent = `클로드 ${(info ? info.name : m.claude) || "기본"}${m.claude_effort ? " · " + effortName(m.claude_effort) : ""}`;
  line.title = line.textContent;
}
async function saveModels(patch) {
  const body = { claude: modelState?.claude || "", claude_effort: modelState?.claude_effort || "", ...patch };
  const info = modelInfo(body.claude);
  if (info && body.claude_effort && !info.efforts.includes(body.claude_effort)) body.claude_effort = "";   // 새 모델이 안 받는 강도는 기본으로
  const { res, data } = await postJson("/api/models", body);
  const msg = document.getElementById("m-msg");
  if (!res.ok) { msg.style.color = "var(--bad)"; msg.textContent = data.error || "저장 실패"; return; }
  msg.style.color = "";
  msg.textContent = "저장함 — 다음 작업부터";
  document.activeElement && document.activeElement.blur();
  renderModels(data.models);
}
{
  const sel = document.getElementById("m-claude"), custom = document.getElementById("m-claude-custom");
  sel.addEventListener("change", () => {
    if (sel.value === "__custom__") { custom.classList.remove("hidden"); custom.focus(); return; }
    custom.classList.add("hidden");
    saveModels({ claude: sel.value });
  });
  custom.addEventListener("keydown", e => { if (e.key === "Enter" && custom.value.trim()) saveModels({ claude: custom.value.trim() }); });
  document.getElementById("m-claude-effort").addEventListener("change", e => saveModels({ claude_effort: e.target.value }));
}
