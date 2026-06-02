// game.js — 브라우저 단독 풀 플레이 (GM 내레이션은 데이터 기반 템플릿으로 대체).
import "./style.css";
import {
  SKILLS, ENEMIES, ITEMS, FLOORS, NPCS, RANKERS, QUESTS, STAT_KEYS, POSITIONS,
  BASE_STAT, CREATION_POOL, CREATION_CAP, createCharacter, levelUp, learnableSkills,
  buildCompanion, Combat, check, makeRng, rankResult, pickEvent, priceMult,
} from "./engine.js";

const SAVE_KEY = "tog_full_save";
const $log = document.getElementById("log");
const $actions = document.getElementById("actions");
const $statbar = document.getElementById("statbar");
document.getElementById("menubtn").onclick = () => P && menu();
let P = null;

// ── UI ────────────────────────────────────────────────────────────
const el = (h, c = "") => { const d = document.createElement("div"); d.className = "line " + c; d.innerHTML = h; $log.appendChild(d); $log.scrollTop = $log.scrollHeight; return d; };
const clr = () => ($log.innerHTML = "");
const gm = (t) => el(`<span class="gm">${t}</span>`, "gm-line");
const sys = (t) => el(`<span class="sys">⚙ ${t}</span>`, "sys-line");
function setActions(btns) { $actions.innerHTML = ""; for (const b of btns) { if (!b) continue; const e = document.createElement("button"); e.className = "btn" + (b.cls ? " " + b.cls : ""); e.textContent = b.label; e.onclick = b.onClick; e.disabled = !!b.disabled; $actions.appendChild(e); } }
function bar() { if (!P) return ($statbar.textContent = ""); $statbar.innerHTML = `${P.이름} Lv${P.레벨} · ❤️${P.HP}/${P.최대HP} · 💧${P.신수}/${P.최대신수} · 🪙${P.돈} · ${FLOORS[P.현재층]?.name || P.현재층} · ⭐${P.랭킹.등급}`; }
const save = () => localStorage.setItem(SAVE_KEY, JSON.stringify(P));
const load = () => { const s = localStorage.getItem(SAVE_KEY); return s ? JSON.parse(s) : null; };

// ── 타이틀 ────────────────────────────────────────────────────────
function title() {
  clr(); P = null; bar();
  el(`<h1>탑 (The Tower)</h1>`, "center");
  gm("끝이 보이지 않는 탑. 꼭대기에 닿는 자에겐 가장 간절한 소원이 약속된다. 그러나 매 층의 시험은 봐주지 않는다 — 실패도 죽음도 진짜다.");
  const s = load();
  const b = [{ label: "▶ 새 게임", cls: "primary", onClick: cName }];
  if (s) b.unshift({ label: `↻ 이어하기 (${s.이름} Lv${s.레벨} · ${FLOORS[s.현재층]?.name})`, cls: "primary", onClick: () => { P = s; bar(); enterFloor(P.현재층); } });
  setActions(b);
}

// ── 생성 ──────────────────────────────────────────────────────────
let dr = {};
function cName() {
  clr(); dr = {}; el(`<h2>캐릭터 생성 — 이름</h2>`); gm("탑에 들어선 당신의 이름은?");
  $actions.innerHTML = ""; const w = document.createElement("div"); w.className = "inputrow";
  const i = document.createElement("input"); i.className = "txt"; i.value = "도전자"; i.maxLength = 16;
  const b = document.createElement("button"); b.className = "btn primary"; b.textContent = "다음";
  b.onclick = () => { dr.name = (i.value || "도전자").trim(); cPos(); }; i.onkeydown = (e) => e.key === "Enter" && b.click();
  w.append(i, b); $actions.appendChild(w); i.focus();
}
function cPos() {
  clr(); el(`<h2>포지션</h2>`); gm("어떤 길을 걷겠는가?");
  setActions(Object.entries(POSITIONS).map(([id, n]) => ({ label: `${n.이름} (${n.주력.join("·")})`, onClick: () => { dr.position = id; cOrigin(); } })));
}
function cOrigin() {
  clr(); el(`<h2>출신</h2>`); gm("정식 절차의 <b>일반 도전자</b>인가, 제 발로 문을 연 <b>이레귤러</b>(고위험 고성장)인가?");
  setActions([{ label: "일반 도전자", onClick: () => { dr.irregular = false; cStat(); } }, { label: "이레귤러", cls: "danger", onClick: () => { dr.irregular = true; cStat(); } }]);
}
function cStat() {
  clr(); const info = POSITIONS[dr.position]; const al = Object.fromEntries(STAT_KEYS.map((k) => [k, 0])); let rem = CREATION_POOL;
  el(`<h2>스탯 배분</h2>`); gm(`${CREATION_POOL}점 배분. 기본 ${BASE_STAT}, <b>${info.주력.join("·")}</b> +2.`);
  const box = el(`<div id="al"></div>`).querySelector("#al");
  const rn = () => { box.innerHTML = `<div class="remain">남은: <b>${rem}</b></div>`; for (const k of STAT_KEYS) { const base = BASE_STAT + (info.주력.includes(k) ? 2 : 0); const v = base + al[k]; const r = document.createElement("div"); r.className = "allocrow"; r.innerHTML = `<span class="sname">${k}</span><span class="sval">${v}</span>`; const m = document.createElement("button"); m.className = "mini"; m.textContent = "−"; m.onclick = () => al[k] > 0 && (al[k]--, rem++, rn()); const p = document.createElement("button"); p.className = "mini"; p.textContent = "+"; p.onclick = () => rem > 0 && v < CREATION_CAP && (al[k]++, rem--, rn()); r.append(m, p); box.appendChild(r); } };
  rn();
  setActions([{ label: "✔ 생성", cls: "primary", onClick: () => { P = createCharacter({ name: dr.name, position: dr.position, irregular: dr.irregular, alloc: al }); save(); bar(); clr(); gm(`<b>${P.이름}</b> — ${info.이름}${P.이레귤러여부 ? " · 이레귤러" : ""} 으로 탑에 들어섰다.`); sys(`HP ${P.최대HP} · 신수 ${P.최대신수} · 시작 스킬 ${P.배운스킬.map((s) => SKILLS[s].name).join(", ")}`); setActions([{ label: "탑을 오른다 ▶", cls: "primary", onClick: () => enterFloor("f01") }]); } }]);
}

// ── 메뉴(시트) ────────────────────────────────────────────────────
function menu() {
  const back = $log.innerHTML, ba = $actions.innerHTML;
  clr(); el(`<h2>${P.이름} — 정보</h2>`);
  el(`<b>${POSITIONS[P.포지션].이름}</b>${P.이레귤러여부 ? " · 이레귤러" : ""} · Lv${P.레벨} (EXP ${P.경험치})`);
  el(`스탯 — ${STAT_KEYS.map((k) => `${k} ${P.스탯[k]}`).join(" · ")}`);
  el(`❤️ ${P.HP}/${P.최대HP} · 💧 ${P.신수}/${P.최대신수} · 🪙 ${P.돈} · 명성 ${P.명성} · 악명 ${P.악명}`);
  el(`스킬 — ${P.배운스킬.map((s) => SKILLS[s].name).join(", ")}`);
  el(`장비 — ${["무기", "방어구", "장신구"].map((s) => `${s}:${P.장비[s]?.이름 || "—"}`).join(" · ")}`);
  el(`동료 — ${P.동료.length ? P.동료.map((c) => c.이름).join(", ") : "없음"}`);
  el(`인벤토리 — ${P.인벤토리.map((i) => `${i.이름}×${i.수량}`).join(", ") || "비었음"}`);
  el(`완료 퀘스트 — ${P.완료퀘스트.length}건 · 클리어 층 — ${P.클리어층.length}곳`);
  const rk = rankResult(P);
  el(`<h3>랭킹 — ${rk.등급} (점수 ${rk.점수}, ${rk.순위}위)</h3>`);
  el(`<div class="board2">${rk.board.slice(0, 8).map((b, i) => `<div class="${b._me ? "me" : ""}">${i + 1}. ${b.name} — ${b.점수.toLocaleString()}</div>`).join("")}</div>`);
  if (rk.상위) el(`바로 위: ${rk.상위.name} (${rk.상위.점수.toLocaleString()})`);
  setActions([{ label: "◀ 돌아가기", cls: "primary", onClick: () => { $log.innerHTML = back; $actions.innerHTML = ba; rebind(); } }]);
}
function rebind() { /* 메뉴 복귀 후 버튼 핸들러는 화면 재호출이 필요 없도록 단순 처리 */ enterFloor(P.현재층, true); }

// ── 층 진입 ───────────────────────────────────────────────────────
function enterFloor(fid, silent) {
  P.현재층 = fid; save(); bar();
  const f = FLOORS[fid]; clr();
  el(`<h2>${f.floor != null ? f.floor + "층 — " : ""}${f.name}</h2>`);
  gm(f.분위기묘사 || "");
  const cleared = P.클리어층.includes(fid);
  if (f.kind === "거점층") return hub(f);
  if (cleared) return travel(f);
  // 비거점 미클리어 → 이벤트 확률 후 시험
  if (!silent && (f.kind !== "갈림길") && Math.random() < 0.45) return event(f, () => presentTest(f));
  presentTest(f);
}

function presentTest(f) {
  if (f.kind === "갈림길") return travel(f, true);
  const t = f.test;
  if (t) gm(`<i>[${t.type}] ${t.name || ""}</i> ${t.설명}`);
  const type = t?.type || "전투시험";
  const enemies = f.적_id목록 || [];
  if (["전투시험", "수호자대결", "생존시험"].includes(type) && enemies.length) {
    const label = type === "수호자대결" ? "가디언에 맞선다 ⚔" : type === "생존시험" ? "버텨낸다 ⚔" : "도전한다 ⚔";
    return setActions([{ label, cls: "danger", onClick: () => combat(enemies, () => clearFloor(f)) }, ...(allyOffer(f) || [])]);
  }
  if (type === "선택시험") return choiceTest(f);
  // 판정형 시험(지력/탐색/추격/포지션/협동)
  const map = { 지력시험: "정신력", 탐색시험: "민첩", 추격시험: "민첩", 포지션시험: POSITIONS[P.포지션].주력[0], 협동시험: "정신력" };
  const stat = map[type] || "정신력";
  const diff = (f.floor || 1) >= 9 ? "어려움" : "보통";
  setActions([{ label: `시험에 임한다 (${stat} 판정) 🎲`, cls: "primary", onClick: () => checkTest(f, stat, diff) }, ...(allyOffer(f) || [])]);
}

function checkTest(f, stat, diff) {
  const r = check(P.스탯, stat, diff, makeRng(Date.now() & 0xffff));
  sys(`${stat} 판정: d100 ${r.roll} ≤ ${r.target}? → <b>${r.outcome}</b>`);
  if (r.success) { gm("시험을 통과했다."); clearFloor(f); }
  else { const dmg = Math.round(P.최대HP * (r.outcome === "대실패" ? 0.35 : 0.18)); P.HP = Math.max(0, P.HP - dmg); save(); bar(); gm(`실패 — 대가를 치른다. HP -${dmg}.`); if (P.HP <= 0) return death(); setActions([{ label: "다시 시도 🎲", onClick: () => checkTest(f, stat, diff) }, { label: "회복약 사용 🧪", onClick: () => { usePotion(); checkTest(f, stat, diff); }, disabled: !hasPotion() }]); }
}

// 선택시험 (도덕/배신)
function choiceTest(f) {
  const opts = f.id === "f14"
    ? [{ label: "동료의 길 — 함께 간다", eff: { 명성: 12, flag: "동료의길" }, txt: "함께 온 이들과 끝까지 가기로 한다." }, { label: "랭커의 길 — 지름길", cls: "danger", eff: { 악명: 6, flag: "랭커의길" }, txt: "랭커의 손을 잡고 지름길을 택한다. 누군가는 등을 돌릴 것이다." }]
    : [{ label: "신의 — 동료를 지킨다", eff: { 명성: 6, flag: "신의" }, txt: "거짓 규칙을 의심하고 동료를 지킨다." }, { label: "실리 — 이득을 취한다", cls: "danger", eff: { 악명: 8, flag: "실리" }, txt: "이득을 위해 비정한 선택을 한다." }, { label: "파훼 — 규칙을 깬다", eff: { 명성: 2, flag: "파훼" }, txt: "주어진 규칙 자체를 부순다." }];
  setActions(opts.map((o) => ({ label: o.label, cls: o.cls, onClick: () => { gm(o.txt); P.명성 += o.eff.명성 || 0; P.악명 += o.eff.악명 || 0; P.플래그[o.eff.flag] = true; sys(`선택 확정(되돌릴 수 없음) — 명성 ${P.명성} · 악명 ${P.악명}`); clearFloor(f); } })));
}

// 동료 영입 제안 (협동층/거점 외에서 1회)
function allyOffer(f) {
  const recruitableHere = { f02: "npc_shibisu", f06: "npc_rak", f13: "npc_yeon" };
  const npcId = recruitableHere[f.id];
  if (!npcId || P.동료.find((c) => c.id === npcId) || NPCS[npcId] == null) return null;
  return [{ label: `🤝 ${NPCS[npcId].이름} 영입 제안`, onClick: () => { const c = buildCompanion(npcId, P.레벨); c.id = npcId; P.동료.push(c); save(); gm(`${c.이름} 이(가) 동료로 합류했다. 전투에 함께한다.`); presentTest(f); } }];
}

// ── 층 클리어 → 보상/퀘스트/랭킹 ──────────────────────────────────
function clearFloor(f) {
  if (!P.클리어층.includes(f.id)) P.클리어층.push(f.id);
  // 전투층이면 처치 기록
  for (const id of f.적_id목록 || []) if (ENEMIES[id] && !P.처치한강적.includes(id)) P.처치한강적.push(id);
  // 보상: 권장전투력 기반 EXP + 약간의 돈/드랍
  const cp = (f.적_id목록 || []).reduce((s, id) => s + (ENEMIES[id]?.권장전투력 || 0), 0) || (f.권장전투력 || 10);
  award(cp * 4 + (f.floor || 1) * 10, "시험 통과");
  P.돈 += (f.floor || 1) * 15 + 20;
  // 퀘스트 마일스톤
  questMilestone(f);
  recalc(); save(); bar();
  // 레벨업 시 스킬 습득 제안
  const learn = learnableSkills(P);
  const next = () => travel(f);
  if (learn.length) setActions([{ label: "📖 스킬 습득", onClick: () => learnScreen(next) }, { label: "다음으로 ▶", cls: "primary", onClick: next }]);
  else setActions([{ label: "다음으로 ▶", cls: "primary", onClick: next }]);
}
const FLOOR_QUEST = { f01: "qm_01", f02: "qm_02", f07: "qm_03", f10: "qm_04", f11: "qm_05", f15: "qm_06" };
function questMilestone(f) {
  const qid = FLOOR_QUEST[f.id]; if (!qid || P.완료퀘스트.includes(qid)) return;
  const q = QUESTS[qid]; if (!q) return;
  P.완료퀘스트.push(qid);
  const rw = q.보상 || {}; P.돈 += rw.돈 || 0; P.명성 += rw.명성 || 0;
  for (const iid of rw.아이템 || []) addItem(iid);
  if (rw.경험치) award(rw.경험치, `퀘스트 보상(${qid})`);
  sys(`📜 퀘스트 완료: ${qid} — 보상 EXP ${rw.경험치 || 0}, 🪙${rw.돈 || 0}${(rw.아이템 || []).length ? ", " + rw.아이템.map((i) => ITEMS[i]?.이름).join("/") : ""}`);
}

function award(amount, src) { P.경험치 += amount; const g = levelUp(P); sys(`경험치 +${amount} (${src})` + (g.length ? ` → ⬆️ Lv${P.레벨} (완전 회복)` : "")); bar(); }
function recalc() { const r = rankResult(P); const prev = P.랭킹.등급; P.랭킹 = { 점수: r.점수, 등급: r.등급, 순위: r.순위 }; if (prev !== r.등급) sys(`⭐ 등급 상승 — <b>${r.등급}</b> (점수 ${r.점수}, ${r.순위}위)`); bar(); }

// ── 이동(연결) ────────────────────────────────────────────────────
function travel(f, branchOnly) {
  const conns = (f.연결 || []).filter((id) => FLOORS[id]);
  if (!conns.length) return ending();
  if (!branchOnly) gm(P.클리어층.includes(f.id) ? "다음 길을 고른다." : "");
  const btns = conns.map((id) => { const nf = FLOORS[id]; const tag = nf.kind === "거점층" ? " 🏕" : nf.kind === "숨겨진층" ? " ❓" : nf.kind === "수호자층" ? " 👹" : ""; return { label: `▶ ${nf.floor != null ? nf.floor + "층 " : ""}${nf.name}${tag}`, cls: nf.kind === "수호자층" ? "danger" : "", onClick: () => enterFloor(id) }; });
  if (f.kind === "거점층") btns.unshift({ label: "🏕 여기 머문다(상점/정비)", onClick: () => hub(f) });
  setActions(btns);
}

// ── 거점층 ────────────────────────────────────────────────────────
function hub(f) {
  const shop = ["potion_small", "potion_large", "shinsu_vial", "shinsu_flask", "leather_armor", "chain_mail", "shinsu_robe", "guardian_plate", "focus_ring", "vitality_charm", "ignition_blade", "tide_scepter", "shadow_edge"];
  const render = () => {
    clr(); el(`<h2>${f.floor}층 — ${f.name}</h2>`); gm(f.분위기묘사 || "");
    gm(`🪙 <b>${P.돈}</b> · ❤️ ${P.HP}/${P.최대HP} · 💧 ${P.신수}/${P.최대신수} · 평판배수 ×${priceMult(P).toFixed(2)}`);
    el(`<div class="shop">${shop.map((id) => { const it = ITEMS[id]; const pr = Math.round(it.가격 * priceMult(P)); return `<div class="shopitem"><b>${it.이름}</b> <span class="grade">[${it.등급}]</span><br><small>${it.설명}</small><br>🪙${pr} <button class="mini buy" data-id="${id}">구매</button>${["무기", "방어구", "장신구"].includes(it.종류) ? ` <button class="mini eq" data-id="${id}">착용</button>` : ""}</div>`; }).join("")}</div>`);
    $log.querySelectorAll(".buy").forEach((b) => (b.onclick = () => { buy(b.dataset.id); render(); acts(); }));
    $log.querySelectorAll(".eq").forEach((b) => (b.onclick = () => { equip(b.dataset.id); render(); acts(); }));
  };
  const acts = () => setActions([
    { label: "🏕 휴식(완전 회복)", onClick: () => { P.HP = P.최대HP; P.신수 = P.최대신수; save(); sys("야영으로 회복했다."); bar(); render(); acts(); } },
    learnableSkills(P).length ? { label: "📖 스킬 습득(수련)", onClick: () => learnScreen(() => { render(); acts(); }) } : null,
    { label: "▶ 떠난다", cls: "primary", onClick: () => travel(f) },
  ]);
  render(); acts();
}
function buy(id) { const it = ITEMS[id]; const pr = Math.round(it.가격 * priceMult(P)); if (P.돈 < pr) return sys("돈 부족."); P.돈 -= pr; addItem(id); save(); sys(`${it.이름} 구매 (🪙-${pr})`); bar(); }
function equip(id) { const it = ITEMS[id]; if (!P.인벤토리.find((x) => x.id === id)) { const pr = Math.round(it.가격 * priceMult(P)); if (P.돈 < pr) return sys("돈 부족."); P.돈 -= pr; addItem(id); } const slot = it.종류; const inv = P.인벤토리.find((x) => x.id === id); if (inv) { inv.수량--; if (inv.수량 <= 0) P.인벤토리 = P.인벤토리.filter((x) => x !== inv); } const prev = P.장비[slot]; if (prev) addItem(prev.id); P.장비[slot] = { id, 이름: it.이름, 종류: slot, 등급: it.등급, 스탯보정: it.스탯보정 || {}, 효과: it.효과 || {} }; save(); sys(`${it.이름} 착용`); bar(); }
function addItem(id) { const it = ITEMS[id]; if (!it) return; const e = P.인벤토리.find((x) => x.id === id); if (e) e.수량++; else P.인벤토리.push({ id, 이름: it.이름, 종류: it.종류, 수량: 1 }); }
const hasPotion = () => P.인벤토리.some((x) => (x.id === "potion_small" || x.id === "potion_large") && x.수량 > 0);
function usePotion() { const p = P.인벤토리.find((x) => (x.id === "potion_large" || x.id === "potion_small") && x.수량 > 0); if (!p) return; const heal = ITEMS[p.id].효과["회복HP"]; const b = P.HP; P.HP = Math.min(P.최대HP, P.HP + heal); p.수량--; if (p.수량 <= 0) P.인벤토리 = P.인벤토리.filter((x) => x !== p); save(); bar(); sys(`🧪 회복 +${P.HP - b}`); }

// ── 스킬 습득 ─────────────────────────────────────────────────────
function learnScreen(back) {
  clr(); el(`<h2>스킬 습득 (수련)</h2>`); const list = learnableSkills(P);
  if (!list.length) { gm("지금 배울 수 있는 스킬이 없다(레벨이 더 필요하다)."); return setActions([{ label: "◀ 돌아가기", cls: "primary", onClick: back }]); }
  gm("배울 스킬을 고르라. (tier가 높을수록 강하다)");
  list.forEach((s) => el(`<div class="shopitem"><b>${s.name}</b> [tier${s.tier}·${s.효과타입}·💧${s.신수소모}]<br><small>${s.설명}</small></div>`));
  setActions(list.map((s) => ({ label: `습득: ${s.name}`, onClick: () => { P.배운스킬.push(s.id); save(); sys(`📖 ${s.name} 습득!`); learnScreen(back); } })).concat([{ label: "◀ 돌아가기", cls: "primary", onClick: back }]));
}

// ── 이벤트 ────────────────────────────────────────────────────────
function event(f, then) {
  const rng = makeRng(Date.now() & 0xffffff); const ev = pickEvent(P, rng);
  if (!ev) return then();
  el(`<div class="evt">🎲 [${ev.종류}] ${ev.설명}</div>`);
  P.발생이벤트.push(ev.id);
  if (!ev.선택지 || !ev.선택지.length) { applyEff(ev.효과 || {}); save(); return setActions([{ label: "계속 ▶", cls: "primary", onClick: then }]); }
  setActions(ev.선택지.map((o) => ({ label: o.id, onClick: () => {
    if (o.판정) { const r = check(P.스탯, o.판정.스탯, o.판정.난이도, rng); sys(`${o.판정.스탯} 판정 → ${r.outcome}`); applyEff(r.success ? (o.결과?.성공 || o.결과 || {}) : (o.결과?.실패 || {})); }
    else applyEff(o.결과 || {});
    save(); bar(); setActions([{ label: "계속 ▶", cls: "primary", onClick: then }]);
  } })));
}
function applyEff(eff) {
  if (eff.명성) P.명성 += eff.명성; if (eff.악명) P.악명 += eff.악명; if (eff.돈) P.돈 += eff.돈; if (eff.경험치) award(eff.경험치, "이벤트");
  if (eff.피해) { const d = eff.피해 === "중" ? Math.round(P.최대HP * 0.2) : eff.피해 === "대" ? Math.round(P.최대HP * 0.35) : Math.round(P.최대HP * 0.1); P.HP = Math.max(0, P.HP - d); sys(`피해 -${d}`); }
  if (eff.아이템) for (const i of eff.아이템) addItem(i);
  if (eff.월드플래그) Object.assign(P.플래그, eff.월드플래그);
  bar(); if (P.HP <= 0) death();
}

// ── 전투 ──────────────────────────────────────────────────────────
function combat(enemyIds, onWin) {
  const allies = P.동료 || [];
  const c = new Combat(P, enemyIds, allies, Date.now() & 0xffffff);
  el(`<div class="vs">⚔ ${enemyIds.map((id) => ENEMIES[id].name).join(", ")}${allies.length ? " (동료: " + allies.map((a) => a.이름).join(", ") + ")" : ""}</div>`, "center");
  const board = el(`<div class="board"></div>`).querySelector(".board");
  const refresh = () => { board.innerHTML = c.enemies.map((e) => `<div class="ebar ${e.hp <= 0 ? "dead" : ""}">${e.name} ❤️${e.hp}/${e.hpMax}${e.status.length ? " (" + e.status.map((s) => s.kind).join(",") + ")" : ""}</div>`).join("") + c.allies.map((a) => `<div class="abar ${a.hp <= 0 ? "dead" : ""}">${a.name} ❤️${a.hp}/${a.hpMax}</div>`).join("") + `<div class="pbar">${c.player.name} ❤️${c.player.hp}/${c.player.hpMax} 💧${c.player.shinsu}/${c.player.shinsuMax}</div>`; };
  refresh();
  const turn = () => {
    if (c.status !== "ongoing") return fin();
    const btns = c.player.skills.map((id) => { const s = SKILLS[id]; return { label: `${s.name} (${s.효과타입}${s.신수소모 ? "·💧" + s.신수소모 : ""})`, disabled: c.player.shinsu < s.신수소모, onClick: () => act({ type: "skill", skill: id, target: c.living("enemy")[0]?.runtimeId }) }; });
    btns.push({ label: "🛡 방어", onClick: () => act({ type: "defend" }) });
    if (hasPotion()) btns.push({ label: "🧪 회복약", onClick: () => { const heal = ITEMS[hpItem()].효과["회복HP"]; const b = c.player.hp; c.player.hp = Math.min(c.player.hpMax, c.player.hp + heal); consume(hpItem()); el(`<span class="dmg-heal">🧪 회복 +${c.player.hp - b}</span>`, "combat"); refresh(); act({ type: "pass" }); } });
    setActions(btns);
  };
  const act = (a) => { for (const l of c.playerAction(a)) el(fmt(l), "combat"); refresh(); if (c.status === "ongoing") { el(`<div class="rdiv">— ${c.round}R —</div>`, "center"); turn(); } else fin(); };
  const fin = () => { refresh(); P.HP = Math.max(0, c.player.hp); P.신수 = c.player.shinsu; save(); bar(); if (c.status === "victory") { el(`<div class="win">🏆 승리! (${c.round}R)</div>`, "center"); onWin(); } else death(); };
  turn();
}
const hpItem = () => (P.인벤토리.find((x) => x.id === "potion_large" && x.수량 > 0) ? "potion_large" : "potion_small");
function consume(id) { const p = P.인벤토리.find((x) => x.id === id); if (p) { p.수량--; if (p.수량 <= 0) P.인벤토리 = P.인벤토리.filter((x) => x !== p); } }
function fmt(l) {
  if (l.event) return `<span class="ev">${l.event}</span>`;
  if (l.reason) return `<span class="ev">${l.atk}: ${l.skill} (${l.reason})</span>`;
  let s = `<b>${l.atk}</b>→${l.def}·${l.skill}`;
  if (l.heal != null) return `<span class="dmg-heal">${s} 회복+${l.heal}</span>`;
  if (l.status && l.damage == null) return `${s} <span class="status">${l.status}</span>`;
  if (l.hit === false) return `<span class="miss">${s} 빗나감</span>`;
  let d = l.damage != null ? ` <span class="dmg">${l.damage}피해</span>${l.crit ? "💥" : ""}` : "";
  if (l.lifesteal) d += ` <span class="dmg-heal">(흡혈+${l.lifesteal})</span>`;
  return s + d;
}

// ── 사망/엔딩 ─────────────────────────────────────────────────────
function death() {
  el(`<div class="dead-msg">☠️ 당신은 탑에서 스러졌다. (봐주기 없음)</div>`, "center");
  gm("탑은 정직하다. 무모함에는 대가가 따른다.");
  localStorage.removeItem(SAVE_KEY);
  setActions([{ label: "처음으로", cls: "primary", onClick: title }]);
}
function ending() {
  clr(); el(`<h1>🎉 정점에 닿다</h1>`, "center");
  const r = rankResult(P);
  gm(`<b>${P.이름}</b> — Lv${P.레벨} · 랭킹 ${r.등급}(점수 ${r.점수}, ${r.순위}위). 더 오를 층이 없다… 적어도 지금은.`);
  gm("본편의 더 깊은 이야기는 <code>tower-of-god/</code> 에서 <code>claude</code>를 GM으로 두고 이어집니다.");
  setActions([{ label: "정보 보기", onClick: menu }, { label: "처음으로", cls: "primary", onClick: title }]);
}

title();
