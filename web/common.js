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
// AI 답(마크다운)을 읽기 좋게 — 먼저 전부 esc 해서 AI 가 쓴 HTML 은 실행되지 않게 하고, 그 위에 서식만 입힌다.
// 제목(# ~ ####) · 굵게 · 기울임 · `코드` · 코드 블록 · 목록(- * 1.) · 체크(- [ ]) · 표 · 인용(>) · 구분선 · 링크(http/https 만)
function mdInline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(text) {
  const lines = esc(String(text ?? "").replace(/\r/g, "")).split("\n");
  const out = [];
  let i = 0;
  const isTable = l => /^\s*\|.*\|\s*$/.test(l);
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {                       // 코드 블록
      const buf = []; i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push(`<pre class="md-code">${buf.join("\n")}</pre>`); continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { out.push(`<h${h[1].length + 2} class="md-h">${mdInline(h[2])}</h${h[1].length + 2}>`); i++; continue; }
    if (/^\s*(---|\*\*\*)\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
    if (/^\s*&gt;\s?/.test(line)) {                   // 인용
      const buf = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*&gt;\s?/, ""));
      out.push(`<blockquote>${buf.map(mdInline).join("<br>")}</blockquote>`); continue;
    }
    if (isTable(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {   // 표
      const cells = l => l.trim().replace(/^\||\|$/g, "").split("|").map(x => mdInline(x.trim()));
      const head = cells(line); i += 2;
      const rows = [];
      while (i < lines.length && isTable(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<div class="md-table"><table><tr>${head.map(x => `<th>${x}</th>`).join("")}</tr>${rows.map(r => `<tr>${r.map(x => `<td>${x}</td>`).join("")}</tr>`).join("")}</table></div>`);
      continue;
    }
    const li = /^(\s*)([-*]|\d+[.)])\s+(.*)$/.exec(line);
    if (li) {                                           // 목록(한 단계 들여쓰기까지)
      const ordered = /\d/.test(li[2]);
      const items = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (!m) { if (lines[i].trim() && items.length && /^\s{2,}/.test(lines[i])) { items[items.length - 1].text += " " + lines[i].trim(); i++; continue; } break; }
        let body = m[3], cls = "";
        const box = /^\[( |x|X)\]\s+(.*)$/.exec(body);
        if (box) { cls = box[1] === " " ? "todo" : "done"; body = (box[1] === " " ? "☐ " : "☑ ") + box[2]; }
        items.push({ deep: m[1].length >= 2, text: body, cls });
        i++;
      }
      const tag = ordered ? "ol" : "ul";
      let html = `<${tag} class="md-list">`;
      for (const it of items) html += `<li class="${it.deep ? "deep " : ""}${it.cls}">${mdInline(it.text)}</li>`;
      out.push(html + `</${tag}>`); continue;
    }
    if (!line.trim()) { i++; continue; }
    const buf = [];                                     // 문단
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*([-*]|\d+[.)])\s|\s*```|\s*&gt;)/.test(lines[i]) && !isTable(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${buf.map(mdInline).join("<br>")}</p>`);
  }
  return out.join("");
}
// 미리보기 — 서식을 걷어 낸 앞부분(접혀 있을 때 보인다)
function mdPlain(text, n = 160) {
  const s = String(text ?? "").replace(/```[\s\S]*?```/g, " ").replace(/^\s*\|?[\s:|-]+\|?\s*$/gm, " ").replace(/^#+\s*/gm, "").replace(/^\s*[-*]\s+(\[[ xX]\]\s+)?/gm, "· ")
    .replace(/\*\*|__|`/g, "").replace(/\|/g, " ").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
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

// ── AI 모델 · 추론 강도(사이드바 아래) — 추가한 AI 마다 따로. 다음 작업부터 적용. 목록은 그 AI 프로그램이 받아 둔 것을 서버가 읽어 준다 ──
document.getElementById("models").innerHTML = `
  <details id="m-fold">
    <summary><span class="mtitle">AI 모델</span><span class="mpicked" id="m-picked"></span></summary>
    <div class="mbody">
    <label>AI<select id="m-which"></select></label>
    <label><span id="m-ai">모델</span><select id="m-model"></select></label>
    <input id="m-custom" class="hidden" placeholder="모델 이름 (Enter 로 저장)" spellcheck="false">
    <label id="m-effort-l">추론 강도<select id="m-effort"></select></label>
    <p class="mnote" id="m-hint">다음 작업부터 적용 · 도는 작업은 그대로</p>
    <span class="mmsg" id="m-msg"></span>
    </div>
  </details>`;
{
  const fold = document.getElementById("m-fold");
  try { fold.open = localStorage.getItem("memodesk.models.open") === "1"; } catch { /* 저장소를 못 쓰면 접힌 채로 */ }
  fold.addEventListener("toggle", () => { try { localStorage.setItem("memodesk.models.open", fold.open ? "1" : "0"); } catch { /* 무시 */ } });
}
let modelState = null, modelWhich = "";
try { modelWhich = localStorage.getItem("memodesk.models.which") || ""; } catch { /* 무시 */ }
const effortName = e => (modelState && modelState.effort_label[e]) || e;
const currentModel = () => (modelState?.ais || []).find(a => a.ai === modelWhich) || null;
const modelInfo = id => (currentModel()?.models || []).find(x => x.id === id) || null;
function renderModels(m) {
  if (!m) return;
  modelState = m;
  const list = m.ais || [];
  if (!list.some(a => a.ai === modelWhich)) modelWhich = list[0]?.ai || "";
  const which = document.getElementById("m-which"), sel = document.getElementById("m-model"), custom = document.getElementById("m-custom");
  const effortSel = document.getElementById("m-effort");
  const cur = currentModel();
  if (![which, sel, custom, effortSel].includes(document.activeElement)) {   // 고르는 중인 칸은 새로고침이 덮지 않는다
    const wh = list.map(a => `<option value="${esc(a.ai)}">${esc(a.name)}</option>`).join("");
    if (which.dataset.sig !== wh) { which.innerHTML = wh; which.dataset.sig = wh; }
    which.value = modelWhich;
    which.disabled = !list.length;
    sel.disabled = !cur;
    document.getElementById("m-ai").textContent = cur ? `${cur.name} 모델` : "모델";
    document.getElementById("m-hint").textContent = cur ? `${cur.hint} · 다음 작업부터 적용` : "먼저 [환경 점검]에서 AI 를 추가하세요";
    document.getElementById("m-effort-l").classList.toggle("hidden", !cur || !cur.has_effort);
    const models = cur?.models || [], known = models.some(x => x.id === cur?.model);
    const opt = x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`;
    const main = models.filter(x => x.main), rest = models.filter(x => !x.main);
    const html = `<option value="">기본</option>`
      + (rest.length ? `<optgroup label="주 모델">${main.map(opt).join("")}</optgroup><optgroup label="그 밖의 버전">${rest.map(opt).join("")}</optgroup>` : main.map(opt).join(""))
      + `<option value="__custom__">직접 입력…</option>`;
    if (sel.dataset.sig !== html) { sel.innerHTML = html; sel.dataset.sig = html; }
    sel.value = cur && cur.model && !known ? "__custom__" : (cur?.model || "");
    custom.classList.toggle("hidden", !(cur && cur.model && !known));
    if (cur && cur.model && !known) custom.value = cur.model;
    const info = modelInfo(cur?.model);
    const efforts = info && info.efforts.length ? info.efforts : ["low", "medium", "high"];
    const first = info && info.recommended ? `기본 (추천: ${effortName(info.recommended)})` : "기본";
    const eh = `<option value="">${esc(first)}</option>` + efforts.map(e => `<option value="${e}">${esc(effortName(e))}</option>`).join("");
    if (effortSel.dataset.sig !== eh) { effortSel.innerHTML = eh; effortSel.dataset.sig = eh; }
    effortSel.value = efforts.includes(cur?.effort) ? cur.effort : "";
  }
  const line = document.getElementById("m-picked");
  line.textContent = list.length ? list.map(a => `${a.name} · ${(a.models.find(x => x.id === a.model)?.name || a.model) || "기본"}`).join(" / ") : "추가한 AI 가 없습니다";
  line.title = line.textContent;
}
async function saveModels(patch) {
  const cur = currentModel();
  if (!cur) return;
  const body = { ai: cur.ai, model: cur.model || "", effort: cur.effort || "", ...patch };
  const info = modelInfo(body.model);
  if (info && body.effort && info.efforts.length && !info.efforts.includes(body.effort)) body.effort = "";   // 새 모델이 안 받는 강도는 기본으로
  const { res, data } = await postJson("/api/models", body);
  const msg = document.getElementById("m-msg");
  if (!res.ok) { msg.style.color = "var(--bad)"; msg.textContent = data.error || "저장 실패"; return; }
  msg.style.color = "";
  msg.textContent = `저장함 — ${cur.name} · 다음 작업부터`;
  document.activeElement && document.activeElement.blur();
  renderModels(data.models);
}
{
  const which = document.getElementById("m-which"), sel = document.getElementById("m-model"), custom = document.getElementById("m-custom");
  which.addEventListener("change", () => {
    modelWhich = which.value;
    try { localStorage.setItem("memodesk.models.which", modelWhich); } catch { /* 무시 */ }
    which.blur(); renderModels(modelState);
  });
  sel.addEventListener("change", () => {
    if (sel.value === "__custom__") { custom.classList.remove("hidden"); custom.focus(); return; }
    custom.classList.add("hidden");
    saveModels({ model: sel.value });
  });
  custom.addEventListener("keydown", e => { if (e.key === "Enter" && custom.value.trim()) saveModels({ model: custom.value.trim() }); });
  document.getElementById("m-effort").addEventListener("change", e => saveModels({ effort: e.target.value }));
}
