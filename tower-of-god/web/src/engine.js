// engine.js — engine/resolve.py·character.py 의 결정론적 로직을 JS로 충실히 포팅.
// 수치 공식·상수는 파이썬 엔진과 동일하게 유지(밸런스 보존).

import skillsRaw from "./data/skills.json";
import enemiesRaw from "./data/enemies.json";
import itemsRaw from "./data/items.json";

export const SKILLS = Object.fromEntries(skillsRaw.skills.map((s) => [s.id, s]));
export const ENEMIES = enemiesRaw.enemies;
export const ITEMS = itemsRaw.items;
export const STAT_KEYS = ["근력", "민첩", "체력", "신수조작", "신수저항", "정신력"];

// ── 밸런스 상수 (resolve.py 와 동일) ──────────────────────────────
const STAT_NEUTRAL = 10;
const HIT_BASE = 75, HIT_AGI_W = 2, HIT_MIN = 5, HIT_MAX = 95;
const DMG_STAT_W = 1.2, DMG_BASE = 5, RES_W = 1.5, CRIT_MULT = 1.5;
const HEAL_STAT_W = 1.0, HEAL_BASE = 8;
const POSITION_STAT = {
  fisherman: "근력", spear_bearer: "민첩", light_bearer: "신수조작",
  wave_controller: "신수조작", scout: "민첩", anima: "신수조작",
};
const HEAL_SKILLS = new Set(["wave_01", "wave_05"]);
const LIFESTEAL_SKILLS = new Set(["anima_07"]);
const BASIC_ATTACK = {
  id: "_basic", name: "기본 공격", position: null, tier: 1,
  신수소모: 0, 효과타입: "피해", 배율: 1.0, 쿨다운: 0,
};

// 캐릭터 생성/성장 상수 (character.py 와 동일)
export const BASE_STAT = 8, CREATION_POOL = 12, CREATION_CAP = 18;
export const STAT_PER_LEVEL = 3, IRREGULAR_BONUS = 1;
export const POSITIONS = {
  fisherman:       { 이름: "낚시꾼",   주력: ["근력", "체력"],     시작: ["fish_01", "fish_02", "fish_03"] },
  spear_bearer:    { 이름: "창지기",   주력: ["민첩", "근력"],     시작: ["spear_01", "spear_02", "spear_03"] },
  light_bearer:    { 이름: "등대지기", 주력: ["정신력", "신수조작"], 시작: ["light_01", "light_02", "light_03"] },
  wave_controller: { 이름: "파도잡이", 주력: ["신수조작", "신수저항"], 시작: ["wave_01", "wave_02", "wave_03"] },
  scout:           { 이름: "탐색꾼",   주력: ["민첩", "정신력"],   시작: ["scout_01", "scout_02", "scout_03"] },
  anima:           { 이름: "애니마",   주력: ["정신력", "신수조작"], 시작: ["anima_01", "anima_02", "anima_03"] },
};

export const deriveHpMax = (stats, level) => 30 + stats["체력"] * 4 + level * 2;
export const deriveShinsuMax = (stats) => 10 + stats["정신력"] * 2 + stats["신수조작"];
export const expToNext = (level) => Math.round(60 * Math.pow(level, 1.5));

// ── 결정론 난수 (mulberry32) ──────────────────────────────────────
export function makeRng(seed) {
  let a = (seed >>> 0) || (Date.now() >>> 0);
  return {
    next() {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    },
    d100() { return Math.floor(this.next() * 100) + 1; },
  };
}

// ── 캐릭터 생성 ───────────────────────────────────────────────────
export function createCharacter({ name, position, irregular, alloc }) {
  const info = POSITIONS[position];
  const stats = Object.fromEntries(STAT_KEYS.map((k) => [k, BASE_STAT]));
  info.주력.forEach((s) => (stats[s] += 2));
  for (const k of STAT_KEYS) stats[k] += alloc[k] || 0;
  const level = 1;
  const p = {
    이름: name, 포지션: position, 이레귤러여부: !!irregular,
    레벨: level, 경험치: 0, 스탯: stats,
    최대HP: deriveHpMax(stats, level), HP: 0,
    최대신수: deriveShinsuMax(stats), 신수: 0,
    배운스킬: [...info.시작], 인벤토리: [
      { id: "potion_small", 이름: ITEMS["potion_small"].이름, 종류: "소모품", 수량: 2 },
    ],
    장비: { 무기: null, 방어구: null, 장신구: null },
    돈: 50, 현재층: "f01", 명성: irregular ? 0 : 0, 악명: 0,
    랭킹: { 점수: 0, 등급: "무명", 순위: null }, 처치한강적: [],
  };
  p.HP = p.최대HP; p.신수 = p.최대신수;
  return p;
}

export function levelUp(p) {
  const info = POSITIONS[p.포지션] || { 주력: ["근력", "체력"] };
  const order = [...info.주력, ...STAT_KEYS.filter((s) => !info.주력.includes(s))];
  const gains = [];
  while (p.경험치 >= expToNext(p.레벨)) {
    p.경험치 -= expToNext(p.레벨);
    p.레벨 += 1;
    const pts = STAT_PER_LEVEL + (p.이레귤러여부 ? IRREGULAR_BONUS : 0);
    for (let i = 0; i < pts; i++) p.스탯[order[i % order.length]] += 1;
    gains.push(p.레벨);
  }
  p.최대HP = deriveHpMax(p.스탯, p.레벨);
  p.최대신수 = deriveShinsuMax(p.스탯);
  p.HP = p.최대HP; p.신수 = p.최대신수; // 레벨업 시 완전 회복
  return gains;
}

// ── 전투용 액터 생성 (장비 보정 적용) ─────────────────────────────
export function actorFromPlayer(p) {
  const stats = { ...p.스탯 };
  let defReduce = 0, accBonus = 0, hpMax = p.최대HP, spMax = p.최대신수;
  for (const slot of ["무기", "방어구", "장신구"]) {
    const it = p.장비?.[slot];
    if (!it) continue;
    for (const [k, v] of Object.entries(it.스탯보정 || {})) if (k in stats) stats[k] += v;
    const eff = it.효과 || {};
    hpMax += eff["최대HP"] || 0; spMax += eff["최대신수"] || 0;
    defReduce += eff["피해감소"] || 0; accBonus += eff["명중"] || 0;
  }
  return {
    name: p.이름, side: "player", stats, hpMax, hp: Math.min(p.HP, hpMax),
    shinsuMax: spMax, shinsu: Math.min(p.신수, spMax),
    skills: [...p.배운스킬], status: [], _defReduce: Math.min(0.75, defReduce),
    _accBonus: accBonus, runtimeId: "player",
  };
}

export function actorFromEnemy(id, rid) {
  const e = ENEMIES[id];
  return {
    name: e.name, side: "enemy", stats: { ...e.stats }, hpMax: e.hp_max, hp: e.hp,
    shinsuMax: e.shinsu_max, shinsu: e.shinsu, skills: [...(e.skills || [])],
    status: [], _defReduce: 0, _accBonus: 0, runtimeId: rid, enemyId: id, cp: e.권장전투력,
  };
}

const sumStatus = (a, kind) => a.status.filter((s) => s.kind === kind).reduce((x, s) => x + (s.mag || 0), 0);
const hasStatus = (a, kind) => a.status.some((s) => s.kind === kind);
const outgoingMult = (a) => Math.max(0.1, 1 + sumStatus(a, "강화") - sumStatus(a, "약화"));
const incomingMult = (a) => a.status.filter((s) => s.kind === "보호").reduce((m, s) => m * (1 - (s.mag || 0)), 1);
function effAgi(a) {
  let agi = a.stats["민첩"] * Math.max(0, 1 - sumStatus(a, "둔화"));
  return hasStatus(a, "속박") ? 0 : agi;
}
function governing(a, skill) {
  const name = POSITION_STAT[skill.position];
  if (!name) return Math.max(a.stats["근력"], a.stats["민첩"], a.stats["신수조작"]);
  return a.stats[name] ?? STAT_NEUTRAL;
}

// ── 1합 해결 (resolve_exchange 포팅) ──────────────────────────────
export function resolveExchange(rng, atk, def, skill) {
  const cost = skill.신수소모 | 0, etype = skill.효과타입, mult = +skill.배율 || 0;
  const log = { atk: atk.name, def: def.name, skill: skill.name, etype };
  if (atk.shinsu < cost) { log.resolved = false; log.reason = "신수 부족"; return log; }
  atk.shinsu -= cost;

  if (etype === "피해" || etype === "디버프") {
    let acc = HIT_BASE + (effAgi(atk) - effAgi(def)) * HIT_AGI_W + (atk._accBonus || 0);
    acc = Math.max(HIT_MIN, Math.min(HIT_MAX, Math.round(acc)));
    const roll = rng.d100();
    const hit = roll <= acc, crit = hit && roll <= 5;
    log.acc = acc; log.hit = hit; log.crit = crit;
    if (!hit) { log.damage = 0; log.defHp = def.hp; return log; }
    let dmg = 0;
    if (mult > 0) {
      const raw = (governing(atk, skill) * DMG_STAT_W + DMG_BASE) * mult * outgoingMult(atk);
      const mitig = 100 / (100 + def.stats["신수저항"] * RES_W);
      dmg = raw * mitig * incomingMult(def) * (1 - (def._defReduce || 0));
      if (crit) dmg *= CRIT_MULT;
      dmg = Math.max(1, Math.round(dmg));
      def.hp = Math.max(0, def.hp - dmg);
    }
    log.damage = dmg; log.defHp = def.hp;
    if (etype === "디버프") {
      const dur = Math.max(1, skill.tier | 0);
      const kind = mult === 0 ? "속박" : (["fish_06", "wave_04", "wave_08"].includes(skill.id) ? "둔화" : "약화");
      def.status.push({ name: skill.name, kind, mag: mult, dur });
      log.status = kind;
    }
    if (LIFESTEAL_SKILLS.has(skill.id) && dmg > 0) {
      const heal = Math.round(dmg * 0.3);
      atk.hp = Math.min(atk.hpMax, atk.hp + heal); log.lifesteal = heal;
    }
  } else if (etype === "버프") {
    if (HEAL_SKILLS.has(skill.id)) {
      const heal = Math.max(1, Math.round((atk.stats["신수조작"] * HEAL_STAT_W + HEAL_BASE) * mult));
      const before = def.hp; def.hp = Math.min(def.hpMax, def.hp + heal);
      log.heal = def.hp - before; log.defHp = def.hp; return log;
    }
    const dur = Math.max(1, skill.tier | 0);
    def.status.push({ name: skill.name, kind: "강화", mag: mult, dur });
    log.status = "강화";
  } else if (etype === "방어") {
    const dur = Math.max(1, skill.tier | 0);
    def.status.push({ name: skill.name, kind: "보호", mag: Math.min(0.9, mult), dur });
    log.status = "보호";
  } else {
    log.note = "유틸";
  }
  log.resolved = true;
  return log;
}

function enemyChoose(actor) {
  let best = null, bm = -1;
  for (const sid of actor.skills) {
    const s = SKILLS[sid];
    if (!s || !["피해", "디버프"].includes(s.효과타입)) continue;
    if (actor.shinsu < (s.신수소모 | 0)) continue;
    if ((s.배율 || 0) > bm) { best = s; bm = s.배율; }
  }
  return best || BASIC_ATTACK;
}

function tickRound(actors) {
  for (const a of actors) {
    for (const st of a.status) if (st.kind === "출혈" && a.hp > 0) a.hp = Math.max(0, a.hp - Math.max(1, Math.round(a.hpMax * (st.mag || 0.05))));
    a.status.forEach((st) => (st.dur -= 1));
    a.status = a.status.filter((st) => st.dur > 0);
  }
}

// ── 전투 (combat) — UI 가 한 라운드씩 호출 ────────────────────────
export class Combat {
  constructor(player, enemyIds, allies = [], seed) {
    this.rng = makeRng(seed);
    this.player = actorFromPlayer(player);
    this.allies = allies.map((a, i) => ({ ...actorFromPlayer(a), side: "ally", runtimeId: "a" + i }));
    this.enemies = enemyIds.map((id, i) => actorFromEnemy(id, "e" + i));
    this.round = 1; this.status = "ongoing"; this.log = [];
  }
  living(side) { const arr = side === "enemy" ? this.enemies : [this.player, ...this.allies]; return arr.filter((a) => a.hp > 0); }
  target(rid) { return this.enemies.find((e) => e.runtimeId === rid && e.hp > 0) || this.living("enemy")[0]; }

  playerAction(action) {
    if (this.status !== "ongoing") return [];
    const log = [];
    const p = this.player;
    if (hasStatus(p, "속박")) log.push({ event: `${p.name} 속박되어 행동 불가` });
    else if (action.type === "defend") { p.status.push({ name: "방어 태세", kind: "보호", mag: 0.4, dur: 1 }); log.push({ event: `${p.name} 방어 태세(피해 40% 경감)` }); }
    else if (action.type === "skill") {
      const sk = SKILLS[action.skill];
      const self = sk.효과타입 === "버프" || sk.효과타입 === "방어" || HEAL_SKILLS.has(sk.id);
      const tgt = self ? p : this.target(action.target);
      if (!tgt) log.push({ event: "유효한 대상 없음" });
      else log.push(resolveExchange(this.rng, p, tgt, sk));
    } else log.push({ event: `${p.name} 대기` });

    // 동료 AI
    for (const ally of this.allies.filter((a) => a.hp > 0)) {
      const liv = this.living("enemy"); if (!liv.length) break;
      const sk = enemyChoose(ally);
      log.push(resolveExchange(this.rng, ally, liv[0], sk));
    }
    if (!this.living("enemy").length) { this.status = "victory"; this.log = log; return log; }

    // 적 AI — 파티 최저 HP 표적
    for (const e of this.enemies.filter((x) => x.hp > 0).sort((a, b) => effAgi(b) - effAgi(a))) {
      if (hasStatus(e, "속박")) { log.push({ event: `${e.name} 속박되어 행동 불가` }); continue; }
      const party = this.living("player").concat(this.living("ally"));
      if (!party.length) break;
      const tgt = party.sort((a, b) => a.hp - b.hp)[0];
      log.push(resolveExchange(this.rng, e, tgt, enemyChoose(e)));
      if (this.player.hp <= 0) { this.status = "defeat"; this.log = log; return log; }
    }
    tickRound([this.player, ...this.allies, ...this.enemies]);
    if (this.player.hp <= 0) this.status = "defeat";
    else if (!this.living("enemy").length) this.status = "victory";
    else this.round += 1;
    this.log = log;
    return log;
  }
}

// 능력 판정 (check) — 지력/회피 시험 등에 사용
export function check(stats, statName, difficulty, rng) {
  const DIFF = { 아주쉬움: -20, 쉬움: -10, 보통: 0, 어려움: 15, 아주어려움: 30, 극악: 45 };
  const roll = rng.d100();
  let target = 50 + (stats[statName] - STAT_NEUTRAL) * 3 - (DIFF[difficulty] || 0);
  target = Math.max(1, Math.min(99, target));
  const success = roll <= target, margin = target - roll;
  let outcome;
  if (roll >= 96 || (!success && Math.abs(margin) >= 50)) outcome = "대실패";
  else if (roll <= 5 || (success && Math.abs(margin) >= 50)) outcome = "대성공";
  else outcome = success ? "성공" : "실패";
  return { roll, target, outcome, success };
}
