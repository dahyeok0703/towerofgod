// engine.js — 파이썬 engine/* 의 결정론 로직을 JS로 포팅(공식·상수 동일).
import skillsRaw from "./data/skills.json";
import enemiesRaw from "./data/enemies.json";
import itemsRaw from "./data/items.json";
import floorsRaw from "./data/floors.json";
import npcsRaw from "./data/npcs.json";
import factionsRaw from "./data/factions.json";
import rankersRaw from "./data/rankers.json";
import questsRaw from "./data/quests.json";
import eventsRaw from "./data/events.json";

export const SKILLS = Object.fromEntries(skillsRaw.skills.map((s) => [s.id, s]));
export const ENEMIES = enemiesRaw.enemies;
export const ITEMS = itemsRaw.items;
export const FLOORS = Object.fromEntries(floorsRaw.floors.map((f) => [f.id, f]));
export const FLOOR_LIST = floorsRaw.floors;
export const NPCS = npcsRaw.npcs;
export const FACTIONS = factionsRaw.factions;
export const RANKERS = rankersRaw.rankers;
export const QUESTS = questsRaw.quests;
export const EVENTS = eventsRaw.events;
export const STAT_KEYS = ["근력", "민첩", "체력", "신수조작", "신수저항", "정신력"];

// ── 밸런스 상수 (resolve.py) ──────────────────────────────────────
const STAT_NEUTRAL = 10;
const HIT_BASE = 75, HIT_AGI_W = 2, HIT_MIN = 5, HIT_MAX = 95;
const DMG_STAT_W = 1.2, DMG_BASE = 5, RES_W = 1.5, CRIT_MULT = 1.5;
const HEAL_STAT_W = 1.0, HEAL_BASE = 8;
const POSITION_STAT = { fisherman: "근력", spear_bearer: "민첩", light_bearer: "신수조작", wave_controller: "신수조작", scout: "민첩", anima: "신수조작" };
const HEAL_SKILLS = new Set(["wave_01", "wave_05"]);
const LIFESTEAL_SKILLS = new Set(["anima_07"]);
const BASIC_ATTACK = { id: "_basic", name: "기본 공격", position: null, tier: 1, 신수소모: 0, 효과타입: "피해", 배율: 1.0, 쿨다운: 0 };

// 생성/성장 (character.py)
export const BASE_STAT = 8, CREATION_POOL = 12, CREATION_CAP = 18, STAT_PER_LEVEL = 3, IRREGULAR_BONUS = 1;
export const TIER_MIN_LEVEL = { 1: 1, 2: 3, 3: 6, 4: 10, 5: 15 };
export const POSITIONS = {
  fisherman: { 이름: "낚시꾼", 주력: ["근력", "체력"], 시작: ["fish_01", "fish_02", "fish_03"] },
  spear_bearer: { 이름: "창지기", 주력: ["민첩", "근력"], 시작: ["spear_01", "spear_02", "spear_03"] },
  light_bearer: { 이름: "등대지기", 주력: ["정신력", "신수조작"], 시작: ["light_01", "light_02", "light_03"] },
  wave_controller: { 이름: "파도잡이", 주력: ["신수조작", "신수저항"], 시작: ["wave_01", "wave_02", "wave_03"] },
  scout: { 이름: "탐색꾼", 주력: ["민첩", "정신력"], 시작: ["scout_01", "scout_02", "scout_03"] },
  anima: { 이름: "애니마", 주력: ["정신력", "신수조작"], 시작: ["anima_01", "anima_02", "anima_03"] },
};
const COMPANION_BASE_STAT = { 일반: 9, 유망주: 11, 정예: 13, 준랭커: 18, 랭커: 24, 최상위랭커: 30, 전설: 36, 초월: 44 };

export const deriveHpMax = (st, lv) => 30 + st["체력"] * 4 + lv * 2;
export const deriveShinsuMax = (st) => 10 + st["정신력"] * 2 + st["신수조작"];
export const expToNext = (lv) => Math.round(60 * Math.pow(lv, 1.5));

// ── 난수 (mulberry32) ─────────────────────────────────────────────
export function makeRng(seed) {
  let a = (seed >>> 0) || (Date.now() >>> 0);
  return {
    next() { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; },
    d100() { return Math.floor(this.next() * 100) + 1; },
    pick(arr) { return arr[Math.floor(this.next() * arr.length)]; },
  };
}

// ── 캐릭터 ────────────────────────────────────────────────────────
export function createCharacter({ name, position, irregular, alloc }) {
  const info = POSITIONS[position];
  const stats = Object.fromEntries(STAT_KEYS.map((k) => [k, BASE_STAT]));
  info.주력.forEach((s) => (stats[s] += 2));
  for (const k of STAT_KEYS) stats[k] += alloc[k] || 0;
  const p = {
    이름: name, 포지션: position, 이레귤러여부: !!irregular, 레벨: 1, 경험치: 0, 스탯: stats,
    최대HP: deriveHpMax(stats, 1), HP: 0, 최대신수: deriveShinsuMax(stats), 신수: 0,
    배운스킬: [...info.시작],
    인벤토리: [{ id: "potion_small", 이름: ITEMS.potion_small.이름, 종류: "소모품", 수량: 2 }],
    장비: { 무기: null, 방어구: null, 장신구: null },
    돈: 80, 현재층: "f01", 명성: 0, 악명: 0,
    랭킹: { 점수: 0, 등급: "무명", 순위: null }, 처치한강적: [], 완료퀘스트: [],
    동료: [], 클리어층: [], 플래그: {}, 발생이벤트: [], 세력평판: {},
  };
  p.HP = p.최대HP; p.신수 = p.최대신수;
  return p;
}
export function levelUp(p) {
  const info = POSITIONS[p.포지션] || { 주력: ["근력", "체력"] };
  const prim = info.주력;
  const non = STAT_KEYS.filter((s) => !prim.includes(s)); // 비주력(방어/자원 포함)
  const gains = [];
  while (p.경험치 >= expToNext(p.레벨)) {
    p.경험치 -= expToNext(p.레벨); p.레벨 += 1;
    const pts = STAT_PER_LEVEL + (p.이레귤러여부 ? IRREGULAR_BONUS : 0);
    // 주력 2종은 항상 +1, 나머지 포인트는 비주력을 순환 분배(신수저항·정신력 등도 성장).
    p.스탯[prim[0]] += 1; if (prim[1]) p.스탯[prim[1]] += 1;
    for (let k = 0; k < pts - 2; k++) p.스탯[non[(p.레벨 + k) % non.length]] += 1;
    gains.push(p.레벨);
  }
  p.최대HP = deriveHpMax(p.스탯, p.레벨); p.최대신수 = deriveShinsuMax(p.스탯);
  p.HP = p.최대HP; p.신수 = p.최대신수;
  return gains;
}
// 현재 배울 수 있는 스킬(자기 포지션·레벨 충족·미습득)
export function learnableSkills(p) {
  return Object.values(SKILLS).filter((s) => s.position === p.포지션 && !p.배운스킬.includes(s.id) && p.레벨 >= (TIER_MIN_LEVEL[s.tier] || 1));
}

// ── 동료 ──────────────────────────────────────────────────────────
export function buildCompanion(npcId, level) {
  const npc = NPCS[npcId]; const pos = npc.포지션;
  const base = COMPANION_BASE_STAT[npc.정전_강함_등급] || 9;
  const prim = (POSITIONS[pos] || { 주력: ["근력", "체력"] }).주력;
  const stats = Object.fromEntries(STAT_KEYS.map((k) => [k, base]));
  const bump = Math.max(0, Math.floor((level - 1) / 2));
  prim.forEach((s) => (stats[s] += 3 + bump));
  const skills = [...(POSITIONS[pos]?.시작 || [])];
  for (const s of npc.사사가능스킬 || []) if (!skills.includes(s)) skills.push(s);
  return { 이름: npc.이름, 포지션: pos, 레벨: level, 스탯: stats, 최대HP: deriveHpMax(stats, level), HP: deriveHpMax(stats, level), 최대신수: deriveShinsuMax(stats), 신수: deriveShinsuMax(stats), 배운스킬: skills, 장비: {}, npcId };
}

// ── 액터 ──────────────────────────────────────────────────────────
export function actorFromPlayer(p, side = "player", rid = "player") {
  const stats = { ...p.스탯 };
  let defReduce = 0, accBonus = 0, hpMax = p.최대HP, spMax = p.최대신수;
  for (const slot of ["무기", "방어구", "장신구"]) {
    const it = p.장비?.[slot]; if (!it) continue;
    for (const [k, v] of Object.entries(it.스탯보정 || {})) if (k in stats) stats[k] += v;
    const e = it.효과 || {}; hpMax += e["최대HP"] || 0; spMax += e["최대신수"] || 0; defReduce += e["피해감소"] || 0; accBonus += e["명중"] || 0;
  }
  return { name: p.이름, side, stats, hpMax, hp: Math.min(p.HP, hpMax), shinsuMax: spMax, shinsu: Math.min(p.신수, spMax), skills: [...p.배운스킬], status: [], _defReduce: Math.min(0.75, defReduce), _accBonus: accBonus, runtimeId: rid };
}
export function actorFromEnemy(id, rid) {
  const e = ENEMIES[id];
  return { name: e.name, side: "enemy", stats: { ...e.stats }, hpMax: e.hp_max, hp: e.hp, shinsuMax: e.shinsu_max, shinsu: e.shinsu, skills: [...(e.skills || [])], status: [], _defReduce: 0, _accBonus: 0, runtimeId: rid, enemyId: id, cp: e.권장전투력 };
}

const sumS = (a, k) => a.status.filter((s) => s.kind === k).reduce((x, s) => x + (s.mag || 0), 0);
const hasS = (a, k) => a.status.some((s) => s.kind === k);
const outMul = (a) => Math.max(0.1, 1 + sumS(a, "강화") - sumS(a, "약화"));
const inMul = (a) => a.status.filter((s) => s.kind === "보호").reduce((m, s) => m * (1 - (s.mag || 0)), 1);
const effAgi = (a) => (hasS(a, "속박") ? 0 : a.stats["민첩"] * Math.max(0, 1 - sumS(a, "둔화")));
function gov(a, sk) { const n = POSITION_STAT[sk.position]; return n ? (a.stats[n] ?? STAT_NEUTRAL) : Math.max(a.stats["근력"], a.stats["민첩"], a.stats["신수조작"]); }

export function resolveExchange(rng, atk, def, sk) {
  const cost = sk.신수소모 | 0, et = sk.효과타입, mult = +sk.배율 || 0;
  const log = { atk: atk.name, def: def.name, skill: sk.name, etype: et };
  if (atk.shinsu < cost) { log.resolved = false; log.reason = "신수 부족"; return log; }
  atk.shinsu -= cost;
  if (et === "피해" || et === "디버프") {
    let acc = HIT_BASE + (effAgi(atk) - effAgi(def)) * HIT_AGI_W + (atk._accBonus || 0);
    acc = Math.max(HIT_MIN, Math.min(HIT_MAX, Math.round(acc)));
    const roll = rng.d100(); const hit = roll <= acc, crit = hit && roll <= 5;
    log.hit = hit; log.crit = crit;
    if (!hit) { log.damage = 0; log.defHp = def.hp; return log; }
    let dmg = 0;
    if (mult > 0) {
      const raw = (gov(atk, sk) * DMG_STAT_W + DMG_BASE) * mult * outMul(atk);
      dmg = raw * (100 / (100 + def.stats["신수저항"] * RES_W)) * inMul(def) * (1 - (def._defReduce || 0));
      if (crit) dmg *= CRIT_MULT;
      dmg = Math.max(1, Math.round(dmg)); def.hp = Math.max(0, def.hp - dmg);
    }
    log.damage = dmg; log.defHp = def.hp;
    if (et === "디버프") { const dur = Math.max(1, sk.tier | 0); const kind = mult === 0 ? "속박" : (["fish_06", "wave_04", "wave_08"].includes(sk.id) ? "둔화" : "약화"); def.status.push({ name: sk.name, kind, mag: mult, dur }); log.status = kind; }
    if (LIFESTEAL_SKILLS.has(sk.id) && dmg > 0) { const h = Math.round(dmg * 0.3); atk.hp = Math.min(atk.hpMax, atk.hp + h); log.lifesteal = h; }
  } else if (et === "버프") {
    if (HEAL_SKILLS.has(sk.id)) { const h = Math.max(1, Math.round((atk.stats["신수조작"] * HEAL_STAT_W + HEAL_BASE) * mult)); const b = def.hp; def.hp = Math.min(def.hpMax, def.hp + h); log.heal = def.hp - b; log.defHp = def.hp; return log; }
    def.status.push({ name: sk.name, kind: "강화", mag: mult, dur: Math.max(1, sk.tier | 0) }); log.status = "강화";
  } else if (et === "방어") { def.status.push({ name: sk.name, kind: "보호", mag: Math.min(0.9, mult), dur: Math.max(1, sk.tier | 0) }); log.status = "보호"; }
  else log.note = "유틸";
  log.resolved = true; return log;
}
function enemyChoose(a) { let best = null, bm = -1; for (const id of a.skills) { const s = SKILLS[id]; if (!s || !["피해", "디버프"].includes(s.효과타입)) continue; if (a.shinsu < (s.신수소모 | 0)) continue; if ((s.배율 || 0) > bm) { best = s; bm = s.배율; } } return best || BASIC_ATTACK; }
function tick(actors) { for (const a of actors) { for (const st of a.status) if (st.kind === "출혈" && a.hp > 0) a.hp = Math.max(0, a.hp - Math.max(1, Math.round(a.hpMax * (st.mag || 0.05)))); a.status.forEach((s) => (s.dur -= 1)); a.status = a.status.filter((s) => s.dur > 0); } }

export class Combat {
  constructor(player, enemyIds, allies = [], seed) {
    this.rng = makeRng(seed);
    this.player = actorFromPlayer(player);
    this.allies = allies.map((a, i) => actorFromPlayer(a, "ally", "a" + i));
    this.enemies = enemyIds.map((id, i) =>
      typeof id === "string"
        ? actorFromEnemy(id, "e" + i)
        : { ...id, runtimeId: "e" + i, side: "enemy", status: id.status || [], _defReduce: id._defReduce || 0, _accBonus: id._accBonus || 0 });
    this.round = 1; this.status = "ongoing"; this.log = [];
  }
  living(side) { const arr = side === "enemy" ? this.enemies : (side === "ally" ? this.allies : [this.player, ...this.allies]); return arr.filter((a) => a.hp > 0); }
  target(rid) { return this.enemies.find((e) => e.runtimeId === rid && e.hp > 0) || this.living("enemy")[0]; }
  playerAction(action) {
    if (this.status !== "ongoing") return [];
    const log = []; const p = this.player;
    if (hasS(p, "속박")) log.push({ event: `${p.name} 속박` });
    else if (action.type === "defend") { p.status.push({ name: "방어 태세", kind: "보호", mag: 0.4, dur: 1 }); log.push({ event: `${p.name} 방어 태세(피해 40%↓)` }); }
    else if (action.type === "skill") { const sk = SKILLS[action.skill]; const self = sk.효과타입 === "버프" || sk.효과타입 === "방어" || HEAL_SKILLS.has(sk.id); const tgt = self ? p : this.target(action.target); if (tgt) log.push(resolveExchange(this.rng, p, tgt, sk)); }
    else log.push({ event: `${p.name} 대기` });
    for (const al of this.allies.filter((a) => a.hp > 0)) { const liv = this.living("enemy"); if (!liv.length) break; log.push(resolveExchange(this.rng, al, liv[0], enemyChoose(al))); }
    if (!this.living("enemy").length) { this.status = "victory"; this.log = log; return log; }
    for (const e of this.enemies.filter((x) => x.hp > 0).sort((a, b) => effAgi(b) - effAgi(a))) {
      if (hasS(e, "속박")) { log.push({ event: `${e.name} 속박` }); continue; }
      const party = this.living("player").concat(this.living("ally")); if (!party.length) break;
      const tgt = party.sort((a, b) => a.hp - b.hp)[0];
      log.push(resolveExchange(this.rng, e, tgt, enemyChoose(e)));
      if (this.player.hp <= 0) { this.status = "defeat"; this.log = log; return log; }
    }
    tick([this.player, ...this.allies, ...this.enemies]);
    if (this.player.hp <= 0) this.status = "defeat"; else if (!this.living("enemy").length) this.status = "victory"; else this.round += 1;
    this.log = log; return log;
  }
}

export function check(stats, statName, difficulty, rng) {
  const DIFF = { 아주쉬움: -20, 쉬움: -10, 보통: 0, 어려움: 15, 아주어려움: 30, 극악: 45 };
  const roll = rng.d100();
  let target = 50 + (stats[statName] - STAT_NEUTRAL) * 3 - (DIFF[difficulty] || 0);
  target = Math.max(1, Math.min(99, target));
  const success = roll <= target, m = target - roll;
  let outcome = roll >= 96 || (!success && Math.abs(m) >= 50) ? "대실패" : roll <= 5 || (success && Math.abs(m) >= 50) ? "대성공" : success ? "성공" : "실패";
  return { roll, target, outcome, success };
}

// ── 랭킹 (rank.py) ────────────────────────────────────────────────
const TIERS = [[50000, "랭커"], [10000, "준랭커"], [4000, "정예"], [1500, "유망주"], [300, "정규등반자"], [0, "무명"]];
export const floorNum = (id) => (id && id[0] === "p" ? +id.slice(1) : (FLOORS[id]?.floor || 0));
export function rankResult(p) {
  const fn = Math.max(floorNum(p.현재층), ...(p.클리어층 || []).map(floorNum), 0);
  const killCp = (p.처치한강적 || []).reduce((s, id) => s + (ENEMIES[id]?.권장전투력 || 0), 0);
  const score = Math.round(fn * 120 + killCp * 1.5 + (p.완료퀘스트 || []).length * 40 + (p.명성 || 0) * 2 + (p.악명 || 0) * 1.2);
  const tier = (TIERS.find(([n]) => score >= n) || [0, "무명"])[1];
  const board = RANKERS.map((r) => ({ name: r.name, 점수: r.점수, 티어: r.티어 })).concat([{ name: "▶ 당신", 점수: score, _me: true }]).sort((a, b) => b.점수 - a.점수);
  const idx = board.findIndex((b) => b._me);
  return { 점수: score, 등급: tier, 순위: idx + 1, board, 상위: board[idx - 1], 아래: board[idx + 1] };
}

// ── 이벤트 (quest.py trigger) ─────────────────────────────────────
export function pickEvent(p, rng) {
  const f = FLOORS[p.현재층]; const fn = f?.floor || 0; const kind = f?.kind || "";
  const pool = EVENTS.filter((e) => { const c = e.발동조건 || {}; if (fn < (c.최소층번호 || 0)) return false; if (fn > (c.최대층번호 || 9999)) return false; if (c.kind && !c.kind.includes(kind)) return false; return true; });
  if (!pool.length) return null;
  const tot = pool.reduce((s, e) => s + (e.가중치 || 1), 0); let r = rng.next() * tot;
  for (const e of pool) { r -= e.가중치 || 1; if (r <= 0) return e; }
  return pool[pool.length - 1];
}

// 평판 기반 구매가 배수 (economy.md)
export const priceMult = (p) => Math.max(0.7, Math.min(1.3, 1 - (p.명성 || 0) * 0.001 + (p.악명 || 0) * 0.0005));

// ── 134층 탑: 절차적 생성 (손으로 만든 1~15층 이후) ───────────────
export const TOWER_HEIGHT = 134;        // 정전의 탑 높이
export const HANDCRAFTED_TOP = 15;      // 손으로 만든 하층 최상단(floor 15)

// 층 구간(원작 구조 참고): 하층/중층/상층
export function bandOf(n) {
  if (n <= 20) return "하층";
  if (n <= 70) return "중층";
  if (n <= 120) return "상층";
  return "최상층";
}
const ENEMY_NAMES = {
  하층: ["파수 병기", "관문 추적자", "잠복 기관"],
  중층: ["중층 감시자", "강철 사냥개", "신수 포식체"],
  상층: ["상층 집행자", "심연 수호물", "광휘 파괴자"],
  최상층: ["정점의 시험체", "왕좌의 그림자", "최후의 관문수"],
};

// 적은 floor 가 아니라 '플레이어 레벨'에 맞춰 스케일한다(레벨 스케일링).
// 층(n)은 작은 가산 램프로만 작용 → 어떤 레벨이든 공정하고, 과도 레벨이어도 트리비얼하지 않음.
export function genEnemyActor(n, i, isBoss = false, lv = 1) {
  const eff = lv + Math.floor(n / 25);
  // 플레이어보다 살짝 약하게(승부가 나되 출혈은 감당 가능) — 보스만 호각.
  const s = 10 + Math.round(eff * (isBoss ? 0.8 : 0.62));
  // 민첩은 낮게 둔다: 비주력 스탯이라 더디게 크는 플레이어의 명중/회피가 무너지지 않도록(공정).
  const stats = { 근력: s, 민첩: Math.max(6, Math.round(s * 0.5)), 체력: s, 신수조작: Math.max(6, s - 2), 신수저항: Math.round(s * 0.6), 정신력: Math.max(6, s - 3) };
  const finale = n === TOWER_HEIGHT;
  const hp = Math.round((24 + eff * 6.5) * (isBoss ? 1.4 : 1) * (finale ? 1.3 : 1));
  const band = bandOf(n);
  const name = isBoss ? `${n}층 가디언` : `${ENEMY_NAMES[band][i % ENEMY_NAMES[band].length]} (${n}F)`;
  const skills = isBoss ? ["fish_05", "fish_06", "fish_02"] : ["fish_02", "fish_05"];
  return { name, stats, hp, hpMax: hp, shinsu: 80 + n, shinsuMax: 80 + n, skills, status: [], cp: Math.round(n + (isBoss ? 40 : 0)), _proc: true };
}

// floorN(16..134) 의 절차적 층 메타 생성 (lv: 적 스케일 기준 플레이어 레벨)
export function genFloor(n, lv = 1) {
  const band = bandOf(n);
  const isBoss = n % 10 === 0 || n === TOWER_HEIGHT;
  // 거점: 5층마다 + 보스 직후(n%10===1) 회복 보장
  const isHub = !isBoss && (n % 5 === 0 || n % 10 === 1);
  let kind = "시험층", type = "전투시험";
  if (isBoss) { kind = "수호자층"; type = "수호자대결"; }
  else if (isHub) { kind = "거점층"; type = null; }
  else { type = ["전투시험", "생존시험", "지력시험", "탐색시험", "전투시험"][n % 5]; }
  const names = {
    수호자층: `${band} 관문 — ${n}층 수호자의 방`,
    거점층: `${band} 정거장 — ${n}층 쉼터`,
    시험층: `${band} 시험 — ${n}층`,
  };
  const moods = {
    수호자층: `${band}의 관문을 지키는 강대한 가디언이 길을 막는다. 공기가 무겁게 짓눌린다.`,
    거점층: `${band}의 작은 정거장. 등불 아래 상인과 단련장이 있다. 다음 시험 전에 숨을 고른다.`,
    시험층: `${band}의 시험장. 신수의 밀도가 한층 더 높아져 숨쉬는 것조차 무게가 느껴진다.`,
  };
  // 적 수: 후반일수록 다수
  const count = isBoss ? 1 : (n % 7 === 0 ? 2 : 1);
  const enemies = type && ["전투시험", "생존시험", "수호자대결"].includes(type)
    ? Array.from({ length: count }, (_, i) => genEnemyActor(n, i, isBoss, lv)) : [];
  return {
    id: "p" + n, floor: n, name: names[kind], kind, band,
    test: type ? { type, 설명: `${band}의 ${type}. 정직한 난이도다.` } : null,
    분위기묘사: moods[kind], 적_id목록: [], _procEnemies: enemies,
    연결: n < TOWER_HEIGHT ? ["p" + (n + 1)] : [],
    _final: n === TOWER_HEIGHT,
  };
}
