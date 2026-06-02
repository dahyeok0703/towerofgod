#!/usr/bin/env python3
"""엔진 자가 테스트.

  1) 결정론: 동일 seed 로 전투를 두 번 돌려 로그/결과가 동일한지.
  2) 위험성: 약한 플레이어 vs 강한 적이 실제로 위험한지(샘플 전투 3개).

실행: python3 engine/selftest.py
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def auto_battle(player_fixture, enemy_refs, seed, max_rounds=40):
    """플레이어가 매 턴 '가장 배율 높은 사용가능 피해 스킬'로 자동 공격하는 전투."""
    skills = R.load_skills()
    enemies = R.load_enemies()
    player = R._ensure_actor(copy.deepcopy(player_fixture))
    state = R.combat_start(player, enemy_refs, skills, enemies, seed=seed)

    full_log = list(state["log"])
    rounds = 0
    while state["status"] == "ongoing" and rounds < max_rounds:
        action = choose_player_action(state, skills)
        state = R.combat_step(state, action, skills, enemies)
        full_log.extend(state["log"])
        rounds += 1

    return {
        "result": state["status"],
        "rounds": state["round"],
        "player_hp": state["player"]["hp"],
        "player_hp_max": state["player"]["hp_max"],
        "enemies": [{"name": e["name"], "hp": e["hp"], "hp_max": e["hp_max"]}
                    for e in state["enemies"]],
        "log": full_log,
    }


def choose_player_action(state, skills):
    player = state["player"]
    living = [e for e in state["enemies"] if e["hp"] > 0]
    if not living:
        return {"type": "pass"}
    target = living[0]["runtime_id"]
    cds = state["cooldowns"]["player"]
    best, best_mult = None, -1
    for sid in player.get("skills", []):
        sk = skills.get(sid)
        if not sk or sk.get("효과타입") not in ("피해", "디버프"):
            continue
        if player["shinsu"] < int(sk.get("신수소모", 0)):
            continue
        if cds.get(sid, 0) > 0:
            continue
        m = float(sk.get("배율", 0))
        if m > best_mult:
            best, best_mult = sid, m
    if best is None:
        # 신수 부족/쿨다운 → 기본 무소모 스킬 또는 방어
        for sid in player.get("skills", []):
            sk = skills.get(sid)
            if sk and sk.get("효과타입") == "피해" and int(sk.get("신수소모", 0)) == 0:
                return {"type": "skill", "skill": sid, "target": target}
        return {"type": "defend"}
    return {"type": "skill", "skill": best, "target": target}


def test_determinism():
    print("=" * 66)
    print("[1] 결정론 테스트 — 동일 seed 로 두 번 전투")
    print("=" * 66)
    weak = load_fixture("weak_player.json")
    a = auto_battle(weak, ["en_gate_warden"], seed=42)
    b = auto_battle(weak, ["en_gate_warden"], seed=42)
    same = json.dumps(a, ensure_ascii=False, sort_keys=True) == \
        json.dumps(b, ensure_ascii=False, sort_keys=True)
    print(f"  seed=42 결과 A: {a['result']} / {a['rounds']}R / "
          f"플레이어 HP {a['player_hp']}")
    print(f"  seed=42 결과 B: {b['result']} / {b['rounds']}R / "
          f"플레이어 HP {b['player_hp']}")
    print(f"  → 두 실행 완전 동일? {'예 ✅ PASS' if same else '아니오 ❌ FAIL'}")

    c = auto_battle(weak, ["en_gate_warden"], seed=999)
    diff = json.dumps(a, ensure_ascii=False, sort_keys=True) != \
        json.dumps(c, ensure_ascii=False, sort_keys=True)
    print(f"  seed=999 결과 C: {c['result']} / {c['rounds']}R / "
          f"플레이어 HP {c['player_hp']}")
    print(f"  → 다른 seed 는 다른 전개? {'예 ✅' if diff else '아니오 ⚠️'}")
    return same


def summarize(title, res):
    print(f"\n  ◆ {title}")
    print(f"    결과: {res['result'].upper()}  ({res['rounds']}라운드)")
    print(f"    플레이어 HP: {res['player_hp']}/{res['player_hp_max']}")
    for e in res["enemies"]:
        print(f"    적 '{e['name']}' HP: {e['hp']}/{e['hp_max']}")


def test_danger():
    print()
    print("=" * 66)
    print("[2] 위험성 테스트 — 약한 플레이어(Lv1) 샘플 전투 3개")
    print("=" * 66)
    weak = load_fixture("weak_player.json")

    s1 = auto_battle(weak, ["en_guardian_hwerok"], seed=7)
    summarize("샘플1: 약한 플레이어 vs 가디언 '회록' (Lv12) — 무모한 도전",
              s1)
    s2 = auto_battle(weak, ["en_iron_brute"], seed=7)
    summarize("샘플2: 약한 플레이어 vs 강철 거구 (Lv5) — 버거운 상대", s2)
    s3 = auto_battle(weak, ["en_sentinel_doll"], seed=7)
    summarize("샘플3: 약한 플레이어 vs 파수 인형 (Lv1) — 적정 상대", s3)

    print("\n  판정:")
    ok1 = s1["result"] == "defeat"
    ok3 = s3["result"] == "victory"
    print(f"    - 가디언전 패배(위험 정상)? {'예 ✅' if ok1 else '아니오 ❌'}")
    print(f"    - 적정 상대는 승리 가능(밸런스 정상)? {'예 ✅' if ok3 else '아니오 ❌'}")
    print(f"    - 강철 거구전 결과: {s2['result']} "
          f"(플레이어 HP {s2['player_hp']}/{s2['player_hp_max']})")
    return ok1 and ok3


def main():
    d = test_determinism()
    g = test_danger()
    print("\n" + "=" * 66)
    print(f"종합: 결정론 {'PASS' if d else 'FAIL'} / "
          f"위험성 {'PASS' if g else 'FAIL'}")
    print("=" * 66)
    sys.exit(0 if (d and g) else 1)


if __name__ == "__main__":
    main()
