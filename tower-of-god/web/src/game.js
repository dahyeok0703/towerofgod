// game.js — 브라우저 단독 플레이 루프 (GM 역할을 데이터 기반으로 대체).
import "./style.css";
import floorsRaw from "./data/floors.json";
import {
  SKILLS, ENEMIES, ITEMS, STAT_KEYS, POSITIONS, BASE_STAT, CREATION_POOL, CREATION_CAP,
  createCharacter, levelUp, expToNext, Combat, check, makeRng,
} from "./engine.js";

const FLOORS = Object.fromEntries(floorsRaw.floors.map((f) => [f.id, f]));
const SAVE_KEY = "tog_web_save";

const $log = document.getElementById("log");
const $actions = document.getElementById("actions");
const $statbar = document.getElementById("statbar");

let P = null; // player

// ── UI 헬퍼 ───────────────────────────────────────────────────────
function print(html, cls = "") {
  const div = document.createElement("div");
  div.className = "line " + cls;
  div.innerHTML = html;
  $log.appendChild(div);
  $log.scrollTop = $log.scrollHeight;
  return div;
}
function clearLog() { $log.innerHTML = ""; }
function gm(t) { return print(`<span class="gm">${t}</span>`, "gm-line"); }
function sys(t) { return print(`<span class="sys">⚙ ${t}</span>`, "sys-line"); }
function setActions(btns) {
  $actions.innerHTML = "";
  for (const b of btns) {
    const el = document.createElement("button");
    el.className = "btn" + (b.cls ? " " + b.cls : "");
    el.textContent = b.label;
    el.onclick = b.onClick;
    if (b.disabled) el.disabled = true;
    $actions.appendChild(el);
  }
}
function updateStatbar() {
  if (!P) { $statbar.textContent = ""; return; }
  $statbar.innerHTML =
    `${P.이름} · Lv${P.레벨} · ❤️ ${P.HP}/${P.최대HP} · 💧 ${P.신수}/${P.최대신수} · ` +
    `🪙 ${P.돈} · ${FLOORS[P.현재층]?.name || P.현재층} · ⭐${P.랭킹.등급}`;
}
function save() { localStorage.setItem(SAVE_KEY, JSON.stringify(P)); }
function load() { const s = localStorage.getItem(SAVE_KEY); return s ? JSON.parse(s) : null; }

// ── 진행 순서 (floors 1~5 슬라이스) ───────────────────────────────
const FLOW = ["f01", "f02", "f03", "f04", "f05"];

// ── 타이틀 ────────────────────────────────────────────────────────
function titleScreen() {
  clearLog(); P = null; updateStatbar();
  print(`<h1>탑 (The Tower)</h1>`, "center");
  gm("끝이 보이지 않는 탑이 당신 앞에 서 있다. 오르는 자에게는 가장 간절한 소원이 약속된다.");
  gm("그러나 매 층마다 시험이 가로막고, 봐주는 법은 없다. 실패도 죽음도 진짜다.");
  const saved = load();
  const btns = [{ label: "▶ 새 게임", cls: "primary", onClick: creationName }];
  if (saved) btns.unshift({ label: `↻ 이어하기 (${saved.이름} Lv${saved.레벨}, ${FLOORS[saved.현재층]?.name || saved.현재층})`, cls: "primary", onClick: () => { P = saved; updateStatbar(); enterFloor(P.현재층); } });
  setActions(btns);
}

// ── 캐릭터 생성 ───────────────────────────────────────────────────
let draft = {};
function creationName() {
  clearLog(); draft = {};
  print(`<h2>캐릭터 생성 — 이름</h2>`);
  gm("탑에 들어선 당신의 이름은?");
  $actions.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "inputrow";
  const inp = document.createElement("input"); inp.className = "txt"; inp.placeholder = "이름 입력"; inp.maxLength = 16; inp.value = "도전자";
  const btn = document.createElement("button"); btn.className = "btn primary"; btn.textContent = "다음";
  btn.onclick = () => { draft.name = (inp.value || "도전자").trim(); creationPosition(); };
  inp.onkeydown = (e) => { if (e.key === "Enter") btn.click(); };
  wrap.append(inp, btn); $actions.appendChild(wrap); inp.focus();
}
function creationPosition() {
  clearLog();
  print(`<h2>캐릭터 생성 — 포지션</h2>`);
  gm("어떤 길을 걷겠는가? 포지션마다 주력 스탯과 시작 능력이 다르다.");
  setActions(Object.entries(POSITIONS).map(([id, info]) => ({
    label: `${info.이름} (${info.주력.join("·")})`,
    onClick: () => { draft.position = id; creationOrigin(); },
  })));
}
function creationOrigin() {
  clearLog();
  print(`<h2>캐릭터 생성 — 출신</h2>`);
  gm("정식 절차로 들어선 <b>일반 도전자</b>인가, 제 발로 문을 연 <b>이레귤러</b>(고위험 고성장)인가?");
  setActions([
    { label: "일반 도전자", onClick: () => { draft.irregular = false; creationStats(); } },
    { label: "이레귤러 (고위험 고성장)", cls: "danger", onClick: () => { draft.irregular = true; creationStats(); } },
  ]);
}
function creationStats() {
  clearLog();
  const info = POSITIONS[draft.position];
  const alloc = Object.fromEntries(STAT_KEYS.map((k) => [k, 0]));
  let remain = CREATION_POOL;
  print(`<h2>캐릭터 생성 — 스탯 배분</h2>`);
  gm(`${CREATION_POOL}점을 배분하라. 기본 ${BASE_STAT}, <b>${info.주력.join("·")}</b>은 포지션 보정 +2.`);
  const box = print(`<div id="alloc"></div>`).querySelector("#alloc");
  function render() {
    box.innerHTML = `<div class="remain">남은 포인트: <b>${remain}</b></div>`;
    for (const k of STAT_KEYS) {
      const base = BASE_STAT + (info.주력.includes(k) ? 2 : 0);
      const val = base + alloc[k];
      const row = document.createElement("div"); row.className = "allocrow";
      row.innerHTML = `<span class="sname">${k}</span><span class="sval">${val}</span>`;
      const minus = document.createElement("button"); minus.className = "mini"; minus.textContent = "−";
      minus.onclick = () => { if (alloc[k] > 0) { alloc[k]--; remain++; render(); } };
      const plus = document.createElement("button"); plus.className = "mini"; plus.textContent = "+";
      plus.onclick = () => { if (remain > 0 && val < CREATION_CAP) { alloc[k]++; remain--; render(); } };
      row.append(minus, plus); box.appendChild(row);
    }
  }
  render();
  setActions([{ label: "✔ 생성 완료", cls: "primary", onClick: () => {
    P = createCharacter({ name: draft.name, position: draft.position, irregular: draft.irregular, alloc });
    save(); updateStatbar();
    clearLog();
    gm(`<b>${P.이름}</b> — ${POSITIONS[P.포지션].이름}${P.이레귤러여부 ? " · 이레귤러" : ""} 으로 탑에 들어섰다.`);
    sys(`HP ${P.최대HP} · 신수 ${P.최대신수} · 시작 스킬 ${P.배운스킬.map((s) => SKILLS[s].name).join(", ")}`);
    setActions([{ label: "탑을 오른다 ▶", cls: "primary", onClick: () => enterFloor("f01") }]);
  } }]);
}

// ── 층 진입 ───────────────────────────────────────────────────────
function enterFloor(fid) {
  P.현재층 = fid; save(); updateStatbar();
  const f = FLOORS[fid];
  clearLog();
  print(`<h2>${f.floor}층 — ${f.name}</h2>`);
  gm(f.분위기묘사 || "");
  if (fid === "f03") return hubScreen(f);
  if (fid === "f05") return branchScreen(f);
  // 전투/생존 시험
  const enemyIds = combatEnemiesFor(fid);
  const t = f.test;
  if (t) gm(`<i>[${t.type}]</i> ${t.설명}`);
  setActions([{ label: "시험에 도전한다 ⚔", cls: "primary", onClick: () => startCombat(enemyIds, () => afterFloorWin(fid)) }]);
}

function combatEnemiesFor(fid) {
  return ({ f01: ["en_sentinel_doll"], f02: ["en_gate_warden"], f04: ["en_storm_eel", "en_mud_lurker"] }[fid]) || [];
}

function afterFloorWin(fid) {
  const enemyIds = combatEnemiesFor(fid);
  const cp = enemyIds.reduce((s, id) => s + (ENEMIES[id].권장전투력 || 0), 0);
  const exp = cp * 4;
  P.처치한강적.push(...enemyIds);
  awardExp(exp, "전투 보상");
  recalcRank();
  save();
  const next = FLOW[FLOW.indexOf(fid) + 1];
  setActions([{ label: next ? "다음 층으로 ▶" : "🎉 슬라이스 클리어", cls: "primary",
    onClick: () => (next ? enterFloor(next) : ending()) }]);
}

function awardExp(amount, src) {
  P.경험치 += amount;
  const before = P.레벨;
  const gains = levelUp(P);
  sys(`경험치 +${amount} (${src})` + (gains.length ? ` → ⬆️ 레벨업! Lv${P.레벨} (HP·신수 완전 회복)` : ""));
  updateStatbar();
}
function recalcRank() {
  // rank.py 간이 이식: 도달층×120 + 강적CP×1.5 + 평판
  const fn = FLOORS[P.현재층]?.floor || 0;
  const killCp = P.처치한강적.reduce((s, id) => s + (ENEMIES[id]?.권장전투력 || 0), 0);
  const score = Math.round(fn * 120 + killCp * 1.5 + P.명성 * 2 + P.악명 * 1.2);
  const tiers = [[50000, "랭커"], [10000, "준랭커"], [4000, "정예"], [1500, "유망주"], [300, "정규등반자"], [0, "무명"]];
  const tier = (tiers.find(([n]) => score >= n) || [0, "무명"])[1];
  const prev = P.랭킹.등급;
  P.랭킹 = { 점수: score, 등급: tier, 순위: P.랭킹.순위 };
  if (prev !== tier) sys(`랭킹 상승 — 등급이 <b>${tier}</b>(으)로 바뀌었다! (점수 ${score})`);
  updateStatbar();
}

// ── 거점층(시장) ──────────────────────────────────────────────────
function hubScreen(f) {
  gm("신수 등불이 흔들리는 시장이다. 다음 시험 전에 정비할 수 있다.");
  const shopItems = ["potion_small", "potion_large", "shinsu_vial", "leather_armor", "chain_mail", "rusty_hook", "training_spear", "scout_dagger"];
  function render() {
    clearLog();
    print(`<h2>${f.floor}층 — ${f.name}</h2>`);
    gm(`보유 🪙 <b>${P.돈}</b> · ❤️ ${P.HP}/${P.최대HP} · 💧 ${P.신수}/${P.최대신수}`);
    if (P.HP < P.최대HP) gm("야영으로 휴식하면 HP·신수를 회복할 수 있다(무료, 1회).");
    print(`<div class="shop">${shopItems.map((id) => {
      const it = ITEMS[id];
      return `<div class="shopitem"><b>${it.이름}</b> <span class="grade">[${it.등급}]</span><br><small>${it.설명}</small><br>🪙${it.가격} <button class="mini buy" data-id="${id}">구매</button> ${["무기","방어구","장신구"].includes(it.종류) ? `<button class="mini eq" data-id="${id}">착용</button>` : ""}</div>`;
    }).join("")}</div>`);
    $log.querySelectorAll("button.buy").forEach((b) => b.onclick = () => buy(b.dataset.id, render));
    $log.querySelectorAll("button.eq").forEach((b) => b.onclick = () => buyEquip(b.dataset.id, render));
  }
  function actions() {
    setActions([
      { label: "🏕 휴식(회복)", onClick: () => { P.HP = P.최대HP; P.신수 = P.최대신수; save(); sys("야영으로 완전히 회복했다."); updateStatbar(); render(); actions(); } },
      { label: "다음 층으로 ▶", cls: "primary", onClick: () => enterFloor("f04") },
    ]);
  }
  render(); actions();
}
function buy(id, after) {
  const it = ITEMS[id];
  if (P.돈 < it.가격) { sys("돈이 부족하다."); return; }
  P.돈 -= it.가격;
  const e = P.인벤토리.find((x) => x.id === id);
  if (e) e.수량++; else P.인벤토리.push({ id, 이름: it.이름, 종류: it.종류, 수량: 1 });
  save(); sys(`${it.이름} 구매 (🪙-${it.가격})`); updateStatbar(); after();
}
function buyEquip(id, after) {
  const it = ITEMS[id];
  if (!P.인벤토리.find((x) => x.id === id)) { if (P.돈 < it.가격) { sys("돈이 부족하다."); return; } buy(id, () => {}); }
  const slot = it.종류;
  const inv = P.인벤토리.find((x) => x.id === id);
  if (inv) { inv.수량--; if (inv.수량 <= 0) P.인벤토리 = P.인벤토리.filter((x) => x !== inv); }
  const prev = P.장비[slot];
  if (prev) { const pe = P.인벤토리.find((x) => x.id === prev.id); if (pe) pe.수량++; else P.인벤토리.push({ id: prev.id, 이름: prev.이름, 종류: slot, 수량: 1 }); }
  P.장비[slot] = { id, 이름: it.이름, 종류: slot, 등급: it.등급, 스탯보정: it.스탯보정 || {}, 효과: it.효과 || {} };
  save(); sys(`${it.이름} 착용 (${slot})`); after();
}

// ── 갈림길 f05 ────────────────────────────────────────────────────
function branchScreen(f) {
  gm("회랑이 둘로 갈라진다. 왼쪽은 힘으로 뚫는 길, 오른쪽은 머리로 푸는 길. 한 번 들어서면 되돌릴 수 없다.");
  setActions([
    { label: "5-A 강철 투기장 (전투) ⚔", cls: "danger", onClick: () => {
        clearLog(); print(`<h2>5-A 강철 투기장</h2>`);
        gm(FLOORS["f05a"]?.분위기묘사 || "사방이 강철 격자. 검투 인형이 깨어난다.");
        startCombat(["en_gladiator_doll"], () => {
          const cp = ENEMIES["en_gladiator_doll"].권장전투력; P.처치한강적.push("en_gladiator_doll");
          awardExp(cp * 4, "전투 보상"); recalcRank(); save();
          setActions([{ label: "🎉 슬라이스 클리어", cls: "primary", onClick: ending }]);
        });
      } },
    { label: "5-B 톱니 미궁 (지력) 🧩", onClick: () => puzzle() },
  ]);
}
function puzzle() {
  clearLog(); print(`<h2>5-B 톱니 미궁</h2>`);
  gm("맞물려 도는 톱니의 순서를 읽어야 한다. 정신을 집중하라(정신력 판정, 어려움).");
  setActions([{ label: "기관을 푼다 (판정) 🎲", cls: "primary", onClick: () => {
    const rng = makeRng((Date.now() & 0xffff));
    const r = check(P.스탯, "정신력", "어려움", rng);
    sys(`정신력 판정: d100 ${r.roll} ≤ ${r.target}? → <b>${r.outcome}</b>`);
    if (r.success) {
      gm("톱니가 맞물리며 길이 열린다. 함정 없이 통과했다.");
      awardExp(120, "지력시험 통과"); recalcRank(); save();
      setActions([{ label: "🎉 슬라이스 클리어", cls: "primary", onClick: ending }]);
    } else {
      const dmg = Math.round(P.최대HP * (r.outcome === "대실패" ? 0.4 : 0.2));
      P.HP = Math.max(0, P.HP - dmg); save(); updateStatbar();
      gm(`기관이 어긋나며 칼날이 솟는다! HP -${dmg}.`);
      if (P.HP <= 0) return death();
      setActions([{ label: "다시 시도 🎲", onClick: puzzle }, { label: "전투로 우회 ⚔", cls: "danger", onClick: () => branchScreen(FLOORS["f05"]) }]);
    }
  } }]);
}

// ── 전투 화면 ─────────────────────────────────────────────────────
function startCombat(enemyIds, onWin) {
  const combat = new Combat(P, enemyIds, [], (Date.now() & 0xffffff));
  print(`<div class="vs">⚔ ${enemyIds.map((id) => ENEMIES[id].name).join(", ")} 와의 전투!</div>`, "center");
  renderCombat(combat, onWin);
}
function renderCombat(combat, onWin) {
  // 적 상태 표시
  const board = print(`<div class="board"></div>`).querySelector(".board");
  const refresh = () => {
    board.innerHTML = combat.enemies.map((e) =>
      `<div class="ebar ${e.hp <= 0 ? "dead" : ""}">${e.name} ❤️${e.hp}/${e.hpMax}${e.status.length ? " " + e.status.map((s) => s.kind).join(",") : ""}</div>`).join("")
      + `<div class="pbar">${combat.player.name} ❤️${combat.player.hp}/${combat.player.hpMax} 💧${combat.player.shinsu}/${combat.player.shinsuMax}</div>`;
  };
  refresh();
  function turn() {
    if (combat.status !== "ongoing") return finish();
    const sk = combat.player.skills.map((id) => SKILLS[id]);
    const btns = sk.map((s) => ({
      label: `${s.name} (${s.효과타입}${s.신수소모 ? " 💧" + s.신수소모 : ""})`,
      disabled: combat.player.shinsu < s.신수소모,
      onClick: () => act({ type: "skill", skill: s.id, target: combat.living("enemy")[0]?.runtimeId }),
    }));
    btns.push({ label: "🛡 방어", onClick: () => act({ type: "defend" }) });
    const pot = P.인벤토리.find((x) => x.id === "potion_small" && x.수량 > 0);
    if (pot) btns.push({ label: `🧪 회복약(${pot.수량})`, onClick: () => { const before = combat.player.hp; combat.player.hp = Math.min(combat.player.hpMax, combat.player.hp + ITEMS["potion_small"].효과["회복HP"]); pot.수량--; if (pot.수량 <= 0) P.인벤토리 = P.인벤토리.filter((x) => x !== pot); print(`<span class="dmg-heal">🧪 회복약 사용 — HP +${combat.player.hp - before}</span>`); refresh(); act({ type: "pass" }, true); } });
    setActions(btns);
  }
  function act(action, skipPlayerLine) {
    const log = combat.playerAction(action);
    for (const l of log) print(fmtLog(l), "combat");
    refresh();
    if (combat.status === "ongoing") { print(`<div class="rdiv">— ${combat.round}라운드 —</div>`, "center"); turn(); }
    else finish();
  }
  function finish() {
    refresh();
    // 전투 결과를 정본 세이브에 반영 (HP/신수만)
    P.HP = Math.max(0, combat.player.hp); P.신수 = combat.player.shinsu; save(); updateStatbar();
    if (combat.status === "victory") { print(`<div class="win">🏆 승리! (${combat.round}라운드)</div>`, "center"); onWin(); }
    else death();
  }
  turn();
}
function fmtLog(l) {
  if (l.event) return `<span class="ev">${l.event}</span>`;
  if (l.reason) return `<span class="ev">${l.atk}: ${l.skill} 실패(${l.reason})</span>`;
  let s = `<b>${l.atk}</b> → ${l.def} · ${l.skill}`;
  if (l.heal != null) return `<span class="dmg-heal">${s} · 회복 +${l.heal}</span>`;
  if (l.status && l.damage == null) return `${s} · <span class="status">${l.status} 부여</span>`;
  if (l.hit === false) return `<span class="miss">${s} · 빗나감</span>`;
  let dmg = l.damage != null ? ` · <span class="dmg">${l.damage} 피해</span>${l.crit ? " 💥치명!" : ""}` : "";
  if (l.lifesteal) dmg += ` <span class="dmg-heal">(흡혈 +${l.lifesteal})</span>`;
  return s + dmg;
}

// ── 사망 / 엔딩 ───────────────────────────────────────────────────
function death() {
  print(`<div class="dead-msg">☠️ 당신은 탑에서 스러졌다. (HP 0 — 봐주기 없음)</div>`, "center");
  gm("탑은 정직하다. 무모함에는 대가가 따른다. 다른 길, 더 나은 준비가 필요했을지도.");
  localStorage.removeItem(SAVE_KEY);
  setActions([{ label: "처음으로", cls: "primary", onClick: titleScreen }]);
}
function ending() {
  clearLog();
  print(`<h1>🎉 1~5층 돌파!</h1>`, "center");
  gm(`<b>${P.이름}</b> — Lv${P.레벨} · 랭킹 ${P.랭킹.등급}(점수 ${P.랭킹.점수}).`);
  gm("여기까지가 이 플레이 슬라이스다. 본편은 이 폴더에서 <code>claude</code>를 GM으로 두고 이어진다.");
  recalcRank();
  setActions([{ label: "계속 탐험(데모 반복)", onClick: () => enterFloor("f05") }, { label: "처음으로", cls: "primary", onClick: titleScreen }]);
}

// ── 부팅 ──────────────────────────────────────────────────────────
titleScreen();
