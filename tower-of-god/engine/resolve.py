#!/usr/bin/env python3
"""결정론적 판정 엔진 (resolve.py)

GM은 전투/판정 시 반드시 이 엔진을 호출하고, 반환된 JSON을 그대로 서술한다.
직접 수치를 지어내지 않는다. (CLAUDE.md 철칙 ②)

명령어
  check   능력 판정 (대성공/성공/실패/대실패)
  attack  전투 1합 해결 (명중·피해·소모·잔여·상태이상)
  combat  턴제 전투 (start/step 단계별 상태 반환 — GM이 중간 묘사 삽입 가능)

난수
  --seed 를 주면 재현 가능, 없으면 진짜 랜덤.
  combat 은 상태(state) 안에 RNG 상태를 직렬화해 단계 간 재현성을 유지한다.

모든 결과는 JSON으로 stdout 에 출력된다(ensure_ascii=False).
"""

import argparse
import json
import os
import random
import sys

# ──────────────────────────────────────────────────────────────────────────
# 경로 / 데이터 로딩
# ──────────────────────────────────────────────────────────────────────────

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(ENGINE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_skills():
    raw = _load_json(os.path.join(DATA_DIR, "skills.json"))
    return {s["id"]: s for s in raw["skills"]}


def load_enemies():
    path = os.path.join(DATA_DIR, "enemies.json")
    if not os.path.exists(path):
        return {}
    return _load_json(path)["enemies"]


# ──────────────────────────────────────────────────────────────────────────
# 밸런스 상수 (4단계 튜닝 포인트 — 여기만 고치면 전반 밸런스가 바뀐다)
# ──────────────────────────────────────────────────────────────────────────

STAT_NEUTRAL = 10          # 스탯 기준점(이 값이면 보정 0)
CHECK_BASE = 50            # 능력 판정 기본 목표치(d100)
CHECK_STAT_W = 3           # 스탯 1당 목표치 보정
CRIT_MARGIN = 50           # 성공/실패 폭이 이 이상이면 대성공/대실패

HIT_BASE = 75              # 기본 명중률(%)
HIT_AGI_W = 2              # (공격 민첩 - 방어 민첩)당 명중 보정
HIT_MIN, HIT_MAX = 5, 95   # 명중률 하한/상한

DMG_STAT_W = 1.2           # 주력 스탯 1당 피해
DMG_BASE = 5               # 피해 기본치
RES_W = 1.5                # 신수저항 1당 경감 계수(체감형)
CRIT_MULT = 1.5            # 치명타 배수
HEAL_STAT_W = 1.0          # 회복: 신수조작 1당
HEAL_BASE = 8

DIFFICULTY = {
    "아주쉬움": -20, "쉬움": -10, "보통": 0,
    "어려움": 15, "아주어려움": 30, "극악": 45,
}

# 스킬 position → 피해/효과 주력 스탯
POSITION_STAT = {
    "fisherman": "근력", "spear_bearer": "민첩", "light_bearer": "신수조작",
    "wave_controller": "신수조작", "scout": "민첩", "anima": "신수조작",
}

HEAL_SKILLS = {"wave_01", "wave_05"}     # 회복 스킬(효과타입은 버프)
LIFESTEAL_SKILLS = {"anima_07"}           # 피해 + 소량 흡혈

# 내부 폴백: 신수 소모/쿨다운 없는 기본 공격 (적 AI가 쓸 수단이 없을 때)
BASIC_ATTACK = {
    "id": "_basic", "name": "기본 공격", "position": None, "tier": 1,
    "신수소모": 0, "효과타입": "피해", "배율": 1.0, "쿨다운": 0,
    "설명": "신수를 두르지 않은 기본 타격.",
}


# ──────────────────────────────────────────────────────────────────────────
# 난수 (재현 가능)
# ──────────────────────────────────────────────────────────────────────────

class RNG:
    """seed 또는 직렬화된 상태로 초기화 가능한 재현형 난수기."""

    def __init__(self, seed=None, state=None):
        self.r = random.Random()
        if state is not None:
            self.r.setstate(_state_from_json(state))
        elif seed is not None:
            self.r.seed(seed)
        # 둘 다 없으면 시스템 엔트로피(진짜 랜덤)

    def d100(self):
        return self.r.randint(1, 100)

    def roll(self, n, sides):
        return sum(self.r.randint(1, sides) for _ in range(n))

    def state_json(self):
        return _state_to_json(self.r.getstate())


def _state_to_json(state):
    version, internal, gauss = state
    return [version, list(internal), gauss]


def _state_from_json(data):
    version, internal, gauss = data
    return (version, tuple(internal), gauss)


# ──────────────────────────────────────────────────────────────────────────
# 액터 로딩 / 파생 수치
# ──────────────────────────────────────────────────────────────────────────

def load_actor(ref, enemies):
    """ref 가 파일 경로면 JSON 로드, enemies 의 id 면 그 스탯블록(복사본) 반환."""
    if ref in enemies:
        actor = json.loads(json.dumps(enemies[ref]))
        actor.setdefault("id", ref)
    elif os.path.exists(ref):
        actor = _load_json(ref)
    else:
        raise SystemExit(json.dumps(
            {"error": f"액터를 찾을 수 없음: {ref} (파일 경로 또는 적 id)"},
            ensure_ascii=False))
    return _ensure_actor(actor)


def _ensure_actor(actor):
    actor.setdefault("stats", {})
    for k in ("근력", "민첩", "체력", "신수조작", "신수저항", "정신력"):
        actor["stats"].setdefault(k, STAT_NEUTRAL)
    s = actor["stats"]
    if "hp_max" not in actor:
        actor["hp_max"] = 30 + s["체력"] * 4 + actor.get("level", 1) * 2
    actor.setdefault("hp", actor["hp_max"])
    if "shinsu_max" not in actor:
        actor["shinsu_max"] = 10 + s["정신력"] * 2 + s["신수조작"]
    actor.setdefault("shinsu", actor["shinsu_max"])
    actor.setdefault("status", [])
    actor.setdefault("skills", [])
    actor.setdefault("name", actor.get("id", "이름없음"))
    return actor


def governing_stat(actor, skill):
    name = POSITION_STAT.get(skill.get("position"), None)
    if name is None:
        # 폴백: 물리/신수 중 큰 쪽
        s = actor["stats"]
        return max(s["근력"], s["민첩"], s["신수조작"])
    return actor["stats"].get(name, STAT_NEUTRAL)


# ── 상태이상 헬퍼 ──────────────────────────────────────────────────────────

def _status_sum(actor, kind):
    return sum(st.get("mag", 0) for st in actor["status"] if st["kind"] == kind)


def _has_status(actor, kind):
    return any(st["kind"] == kind for st in actor["status"])


def outgoing_mult(actor):
    """공격자 강화/약화 반영 피해 배수."""
    return max(0.1, 1 + _status_sum(actor, "강화") - _status_sum(actor, "약화"))


def incoming_mult(actor):
    """방어자 보호막(피해 경감) 반영 배수."""
    mult = 1.0
    for st in actor["status"]:
        if st["kind"] == "보호":
            mult *= (1 - st.get("mag", 0))
    return max(0.0, mult)


def effective_agi(actor):
    slow = _status_sum(actor, "둔화")
    agi = actor["stats"]["민첩"] * max(0.0, 1 - slow)
    if _has_status(actor, "속박"):
        agi = 0
    return agi


# ──────────────────────────────────────────────────────────────────────────
# 1) 능력 판정 (check)
# ──────────────────────────────────────────────────────────────────────────

def do_check(actor, stat, difficulty, dice, rng):
    if stat not in actor["stats"]:
        raise SystemExit(json.dumps(
            {"error": f"알 수 없는 스탯: {stat}"}, ensure_ascii=False))
    diff_mod = DIFFICULTY.get(difficulty, 0)
    stat_val = actor["stats"][stat]

    if dice == "3d6":
        # 3d6: 낮을수록 좋음. 목표치 = (스탯-기준)/2 + 10 - 난이도/4
        roll = rng.roll(3, 6)
        target = round((stat_val - STAT_NEUTRAL) / 2 + 10 - diff_mod / 4)
        target = max(3, min(18, target))
        success = roll <= target
        margin = target - roll
        crit_margin = 6
        nat_crit = roll <= 4
        nat_fumble = roll >= 17
        crit_band = abs(margin) >= crit_margin
    else:  # d100 (기본). 낮을수록 좋음.
        roll = rng.d100()
        target = CHECK_BASE + (stat_val - STAT_NEUTRAL) * CHECK_STAT_W - diff_mod
        target = max(1, min(99, target))
        success = roll <= target
        margin = target - roll
        nat_crit = roll <= 5
        nat_fumble = roll >= 96
        crit_band = abs(margin) >= CRIT_MARGIN

    if nat_fumble or (not success and crit_band):
        outcome = "대실패"
    elif nat_crit or (success and crit_band):
        outcome = "대성공"
    elif success:
        outcome = "성공"
    else:
        outcome = "실패"

    return {
        "command": "check",
        "stat": stat, "stat_value": stat_val,
        "difficulty": difficulty, "difficulty_mod": diff_mod,
        "dice": dice, "roll": roll, "target": target, "margin": margin,
        "outcome": outcome, "success": success,
        "actor": actor.get("name"),
    }


# ──────────────────────────────────────────────────────────────────────────
# 2) 전투 1합 (attack) — combat 의 빌딩블록
# ──────────────────────────────────────────────────────────────────────────

def resolve_exchange(rng, attacker, defender, skill):
    """attacker 가 defender 에게 skill 사용. 액터를 직접 변경하고 로그 dict 반환."""
    cost = int(skill.get("신수소모", 0))
    etype = skill.get("효과타입", "피해")
    mult = float(skill.get("배율", 1.0))
    log = {
        "attacker": attacker.get("name"), "defender": defender.get("name"),
        "skill": skill.get("name"), "skill_id": skill.get("id"),
        "effect_type": etype, "shinsu_cost": cost,
    }

    if attacker["shinsu"] < cost:
        log.update({"resolved": False, "reason": "신수 부족",
                    "attacker_shinsu": attacker["shinsu"]})
        return log
    attacker["shinsu"] -= cost
    log["attacker_shinsu_left"] = attacker["shinsu"]

    # 효과타입별 처리 ------------------------------------------------------
    if etype in ("피해", "디버프"):
        # 명중 판정
        acc = HIT_BASE + (effective_agi(attacker) - effective_agi(defender)) * HIT_AGI_W
        acc = max(HIT_MIN, min(HIT_MAX, round(acc)))
        hit_roll = rng.d100()
        hit = hit_roll <= acc
        crit = hit and (hit_roll <= 5)
        log.update({"accuracy": acc, "hit_roll": hit_roll, "hit": hit, "crit": crit})
        if not hit:
            log["resolved"] = True
            log["damage"] = 0
            log["defender_hp_left"] = defender["hp"]
            return log

        dmg = 0
        if mult > 0:
            gov = governing_stat(attacker, skill)
            raw = (gov * DMG_STAT_W + DMG_BASE) * mult * outgoing_mult(attacker)
            res = defender["stats"]["신수저항"]
            mitig = 100 / (100 + res * RES_W)
            dmg = raw * mitig * incoming_mult(defender)
            if crit:
                dmg *= CRIT_MULT
            dmg = max(1, round(dmg))
            defender["hp"] = max(0, defender["hp"] - dmg)
        log["damage"] = dmg
        log["defender_hp_left"] = defender["hp"]

        # 디버프는 상태이상도 부여
        if etype == "디버프":
            applied = _apply_status(defender, skill, mult)
            if applied:
                log["status_applied"] = applied
        # 흡혈
        if skill.get("id") in LIFESTEAL_SKILLS and dmg > 0:
            heal = round(dmg * 0.3)
            attacker["hp"] = min(attacker["hp_max"], attacker["hp"] + heal)
            log["lifesteal"] = heal
            log["attacker_hp"] = attacker["hp"]

    elif etype == "버프":
        if skill.get("id") in HEAL_SKILLS:
            gov = attacker["stats"]["신수조작"]
            heal = max(1, round((gov * HEAL_STAT_W + HEAL_BASE) * mult))
            before = defender["hp"]
            defender["hp"] = min(defender["hp_max"], defender["hp"] + heal)
            log.update({"resolved": True, "heal": defender["hp"] - before,
                        "defender_hp_left": defender["hp"]})
            return log
        # 일반 버프: 대상(아군/자신)에 강화 부여
        dur = max(1, int(skill.get("tier", 1)))
        defender["status"].append({"name": skill["name"], "kind": "강화",
                                   "mag": mult, "dur": dur})
        log.update({"resolved": True, "status_applied":
                    {"kind": "강화", "mag": mult, "dur": dur}})
        return log

    elif etype == "방어":
        dur = max(1, int(skill.get("tier", 1)))
        defender["status"].append({"name": skill["name"], "kind": "보호",
                                   "mag": min(0.9, mult), "dur": dur})
        log.update({"resolved": True, "status_applied":
                    {"kind": "보호", "mag": min(0.9, mult), "dur": dur}})
        return log

    else:  # 유틸
        log.update({"resolved": True, "note": "유틸리티 효과(수치 비전투). GM 서술."})
        return log

    log["resolved"] = True
    return log


def _apply_status(defender, skill, mult):
    """디버프 스킬에 따른 상태이상 부여. 부여 내용 dict 반환(없으면 None)."""
    sid = skill.get("id", "")
    dur = max(1, int(skill.get("tier", 1)))
    # 결박류(배율 0): 속박, 그 외: 둔화/약화
    if mult == 0:
        st = {"name": skill["name"], "kind": "속박", "mag": 0, "dur": dur}
    elif "둔화" in skill.get("설명", "") or sid in ("fish_06", "wave_04", "wave_08"):
        st = {"name": skill["name"], "kind": "둔화", "mag": mult, "dur": dur}
    else:
        st = {"name": skill["name"], "kind": "약화", "mag": mult, "dur": dur}
    defender["status"].append(st)
    return {"kind": st["kind"], "mag": st["mag"], "dur": st["dur"]}


def do_attack(attacker, defender, skill, rng):
    log = resolve_exchange(rng, attacker, defender, skill)
    return {
        "command": "attack",
        "result": log,
        "attacker_state": _short_state(attacker),
        "defender_state": _short_state(defender),
    }


def _short_state(actor):
    return {
        "name": actor.get("name"),
        "hp": actor["hp"], "hp_max": actor["hp_max"],
        "shinsu": actor["shinsu"], "shinsu_max": actor["shinsu_max"],
        "status": [s["name"] + f"({s['kind']})" for s in actor["status"]],
        "alive": actor["hp"] > 0,
    }


# ──────────────────────────────────────────────────────────────────────────
# 3) 턴제 전투 (combat) — start / step
# ──────────────────────────────────────────────────────────────────────────

def combat_start(player, enemy_refs, skills, enemies, seed=None):
    rng = RNG(seed=seed)
    enemy_actors = []
    for i, ref in enumerate(enemy_refs):
        e = load_actor(ref, enemies)
        e["runtime_id"] = f"e{i}"
        enemy_actors.append(e)
    state = {
        "command": "combat", "phase": "start",
        "seed": seed, "round": 1, "status": "ongoing",
        "rng_state": rng.state_json(),
        "player": player, "enemies": enemy_actors,
        "cooldowns": {"player": {}, **{e["runtime_id"]: {} for e in enemy_actors}},
        "log": [{"event": "전투 시작",
                 "enemies": [e["name"] for e in enemy_actors]}],
        "available_actions": _player_actions(player, skills),
    }
    return state


def combat_step(state, action, skills, enemies):
    if state["status"] != "ongoing":
        state["log"] = [{"event": "전투 종료됨", "status": state["status"]}]
        return state

    rng = RNG(state=state["rng_state"])
    player = _ensure_actor(state["player"])
    enemy_actors = [_ensure_actor(e) for e in state["enemies"]]
    cooldowns = state["cooldowns"]
    log = []

    # ── 플레이어 행동 ──────────────────────────────────────────────────
    if _has_status(player, "속박"):
        log.append({"actor": player["name"], "event": "속박되어 행동 불가"})
    else:
        log.append(_run_player_action(rng, player, enemy_actors, action,
                                      skills, cooldowns))

    living = [e for e in enemy_actors if e["hp"] > 0]
    if not living:
        state.update(_finish(state, player, enemy_actors, rng, log, "victory"))
        return state

    # ── 적 행동 (민첩 순) ─────────────────────────────────────────────
    for enemy in sorted(living, key=lambda e: -effective_agi(e)):
        if enemy["hp"] <= 0:
            continue
        if _has_status(enemy, "속박"):
            log.append({"actor": enemy["name"], "event": "속박되어 행동 불가"})
            continue
        skill = _enemy_choose(enemy, cooldowns[enemy["runtime_id"]], skills)
        ex = resolve_exchange(rng, enemy, player, skill)
        log.append(ex)
        cd = int(skill.get("쿨다운", 0))
        if cd > 0:
            cooldowns[enemy["runtime_id"]][skill["id"]] = cd
        if player["hp"] <= 0:
            state.update(_finish(state, player, enemy_actors, rng, log, "defeat"))
            return state

    # ── 라운드 마감: 상태이상/쿨다운 정리 ────────────────────────────
    _tick_round([player] + enemy_actors, cooldowns, log)
    if player["hp"] <= 0:
        state.update(_finish(state, player, enemy_actors, rng, log, "defeat"))
        return state
    if all(e["hp"] <= 0 for e in enemy_actors):
        state.update(_finish(state, player, enemy_actors, rng, log, "victory"))
        return state

    state.update({
        "phase": "step", "round": state["round"] + 1, "status": "ongoing",
        "rng_state": rng.state_json(), "player": player, "enemies": enemy_actors,
        "cooldowns": cooldowns, "log": log,
        "player_state": _short_state(player),
        "enemies_state": [_short_state(e) for e in enemy_actors],
        "available_actions": _player_actions(player, skills),
    })
    return state


def _run_player_action(rng, player, enemy_actors, action, skills, cooldowns):
    atype = action.get("type", "pass")
    if atype == "pass":
        return {"actor": player["name"], "event": "대기"}
    if atype == "defend":
        player["status"].append({"name": "방어 태세", "kind": "보호",
                                 "mag": 0.4, "dur": 1})
        return {"actor": player["name"], "event": "방어 태세(피해 40% 경감, 1턴)"}
    if atype == "skill":
        sid = action.get("skill")
        skill = skills.get(sid)
        if skill is None:
            return {"actor": player["name"], "error": f"알 수 없는 스킬: {sid}"}
        if sid not in player.get("skills", []):
            return {"actor": player["name"], "error": f"보유하지 않은 스킬: {sid}"}
        if cooldowns["player"].get(sid, 0) > 0:
            return {"actor": player["name"], "error": f"쿨다운 중: {sid}",
                    "남은쿨다운": cooldowns["player"][sid]}
        # 대상 선택
        etype = skill.get("효과타입")
        if etype in ("버프", "방어") or sid in HEAL_SKILLS:
            target = player  # 자기/아군 대상(단순화: 자신)
        else:
            living = [e for e in enemy_actors if e["hp"] > 0]
            tgt_id = action.get("target")
            target = next((e for e in living if e.get("runtime_id") == tgt_id),
                          living[0] if living else None)
        if target is None:
            return {"actor": player["name"], "error": "유효한 대상 없음"}
        ex = resolve_exchange(rng, player, target, skill)
        cd = int(skill.get("쿨다운", 0))
        if cd > 0 and ex.get("resolved"):
            cooldowns["player"][sid] = cd
        return ex
    return {"actor": player["name"], "error": f"알 수 없는 행동: {atype}"}


def _enemy_choose(enemy, enemy_cd, skills):
    """적 AI: 사용 가능한 피해/디버프 스킬 중 배율 최고를 고른다. 없으면 기본 공격."""
    options = []
    for sid in enemy.get("skills", []):
        sk = skills.get(sid)
        if not sk:
            continue
        if sk.get("효과타입") not in ("피해", "디버프"):
            continue
        if enemy["shinsu"] < int(sk.get("신수소모", 0)):
            continue
        if enemy_cd.get(sid, 0) > 0:
            continue
        options.append(sk)
    if not options:
        return BASIC_ATTACK
    return max(options, key=lambda s: float(s.get("배율", 0)))


def _tick_round(actors, cooldowns, log):
    # 출혈 등 도트 처리 → 지속시간 감소 → 만료 제거
    for a in actors:
        for st in a["status"]:
            if st["kind"] == "출혈" and a["hp"] > 0:
                dot = max(1, round(a["hp_max"] * st.get("mag", 0.05)))
                a["hp"] = max(0, a["hp"] - dot)
                log.append({"actor": a["name"], "event": "출혈 피해", "damage": dot})
        for st in a["status"]:
            st["dur"] -= 1
        a["status"] = [st for st in a["status"] if st["dur"] > 0]
    for owner in cooldowns:
        for sid in list(cooldowns[owner].keys()):
            cooldowns[owner][sid] -= 1
            if cooldowns[owner][sid] <= 0:
                del cooldowns[owner][sid]


def _finish(state, player, enemy_actors, rng, log, result):
    return {
        "phase": "end", "status": result, "rng_state": rng.state_json(),
        "round": state["round"], "player": player, "enemies": enemy_actors,
        "cooldowns": state["cooldowns"], "log": log,
        "player_state": _short_state(player),
        "enemies_state": [_short_state(e) for e in enemy_actors],
        "result": result,
    }


def _player_actions(player, skills):
    usable = []
    for sid in player.get("skills", []):
        sk = skills.get(sid)
        if sk:
            usable.append({"skill": sid, "name": sk["name"],
                           "효과타입": sk["효과타입"], "신수소모": sk["신수소모"]})
    return {"skill": usable, "defend": "방어 태세", "pass": "대기"}


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="결정론적 판정 엔진")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="능력 판정")
    p_check.add_argument("--stat", required=True)
    p_check.add_argument("--difficulty", default="보통")
    p_check.add_argument("--actor", required=True)
    p_check.add_argument("--dice", default="d100", choices=["d100", "3d6"])
    p_check.add_argument("--seed", type=int, default=None)

    p_atk = sub.add_parser("attack", help="전투 1합")
    p_atk.add_argument("--attacker", required=True)
    p_atk.add_argument("--defender", required=True)
    p_atk.add_argument("--skill", required=True)
    p_atk.add_argument("--seed", type=int, default=None)

    p_cmb = sub.add_parser("combat", help="턴제 전투(start/step)")
    p_cmb.add_argument("--mode", choices=["start", "step"], default="start")
    p_cmb.add_argument("--attacker", help="(start) 플레이어 액터 경로")
    p_cmb.add_argument("--enemies", help="(start) 적 id 쉼표구분")
    p_cmb.add_argument("--state", help="(step) 전투 상태 JSON 경로")
    p_cmb.add_argument("--action", help="(step) 행동 JSON 문자열")
    p_cmb.add_argument("--seed", type=int, default=None)

    args = parser.parse_args(argv)
    skills = load_skills()
    enemies = load_enemies()

    if args.command == "check":
        rng = RNG(seed=args.seed)
        actor = load_actor(args.actor, enemies)
        _emit(do_check(actor, args.stat, args.difficulty, args.dice, rng))

    elif args.command == "attack":
        rng = RNG(seed=args.seed)
        attacker = load_actor(args.attacker, enemies)
        defender = load_actor(args.defender, enemies)
        skill = skills.get(args.skill)
        if skill is None:
            _emit({"error": f"알 수 없는 스킬: {args.skill}"})
            return
        _emit(do_attack(attacker, defender, skill, rng))

    elif args.command == "combat":
        if args.mode == "start":
            player = load_actor(args.attacker, enemies)
            enemy_refs = [r.strip() for r in (args.enemies or "").split(",") if r.strip()]
            _emit(combat_start(player, enemy_refs, skills, enemies, seed=args.seed))
        else:
            state = _load_json(args.state)
            action = json.loads(args.action) if args.action else {"type": "pass"}
            _emit(combat_step(state, action, skills, enemies))


if __name__ == "__main__":
    main()
