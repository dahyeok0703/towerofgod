#!/usr/bin/env python3
"""장비 회귀 테스트.

동일 seed·동일 스킬로, 장비 착용 전/후의 전투 결과(가하는 피해·받는 피해)가
달라지는지 확인한다. 장비 보정이 resolve.py 에 제대로 연동됐는지 검증.

실행: python3 engine/test_equipment.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R  # noqa: E402

BARE = {
    "name": "맨몸 도전자", "position": "fisherman", "level": 5,
    "stats": {"근력": 12, "민첩": 11, "체력": 12, "신수조작": 8, "신수저항": 8, "정신력": 9},
    "skills": ["fish_02", "fish_05"], "status": [],
    "장비": {"무기": None, "방어구": None, "장신구": None},
}

WEAPON = {"id": "ignition_blade", "이름": "점화 도신", "종류": "무기",
          "스탯보정": {"근력": 6}, "효과": {"명중": 5}}
ARMOR = {"id": "guardian_plate", "이름": "수호 판금", "종류": "방어구",
         "스탯보정": {"체력": 5, "신수저항": 3}, "효과": {"피해감소": 0.08}}


def attack_once(attacker_src, defender_src, skill_id, seed):
    skills = R.load_skills()
    enemies = R.load_enemies()
    atk = R._ensure_actor(copy.deepcopy(attacker_src))
    dfn = (R.load_actor(defender_src, enemies) if isinstance(defender_src, str)
           else R._ensure_actor(copy.deepcopy(defender_src)))
    rng = R.RNG(seed=seed)
    out = R.do_attack(atk, dfn, skills[skill_id], rng)
    return out["result"]


def main():
    print("=" * 64)
    print("장비 회귀 테스트 — 동일 seed/스킬, 착용 전후 비교")
    print("=" * 64)

    # (1) 공격: 무기 착용 시 피해 증가 ----------------------------------
    bare = copy.deepcopy(BARE)
    armed = copy.deepcopy(BARE)
    armed["장비"]["무기"] = WEAPON
    r_bare = attack_once(bare, "en_iron_brute", "fish_05", seed=4)
    r_armed = attack_once(armed, "en_iron_brute", "fish_05", seed=4)
    print("\n[공격] fish_05 → 강철 거구 (seed=4)")
    print(f"  맨몸     : 명중 {r_bare['hit']} 피해 {r_bare['damage']}")
    print(f"  점화 도신: 명중 {r_armed['hit']} 피해 {r_armed['damage']}")
    atk_ok = r_armed["damage"] > r_bare["damage"]
    print(f"  → 무기로 피해 증가? {'예 ✅' if atk_ok else '아니오 ❌'} "
          f"(+{r_armed['damage'] - r_bare['damage']})")

    # (2) 방어: 방어구 착용 시 받는 피해 감소 ---------------------------
    bare_def = copy.deepcopy(BARE)
    armored = copy.deepcopy(BARE)
    armored["장비"]["방어구"] = ARMOR
    # 강철 거구가 같은 스킬로 동일 seed 공격
    brute = R.load_enemies()["en_iron_brute"]
    t_bare = attack_once(brute, bare_def, "fish_05", seed=9)
    t_armored = attack_once(brute, armored, "fish_05", seed=9)
    print("\n[방어] 강철 거구 fish_05 → 도전자 (seed=9)")
    print(f"  맨몸    : 받은 피해 {t_bare['damage']}")
    print(f"  수호 판금: 받은 피해 {t_armored['damage']}")
    def_ok = t_armored["damage"] < t_bare["damage"]
    print(f"  → 방어구로 받는 피해 감소? {'예 ✅' if def_ok else '아니오 ❌'} "
          f"(−{t_bare['damage'] - t_armored['damage']})")

    # (3) 결정론: 동일 입력 두 번 동일 -------------------------------
    a = attack_once(armed, "en_iron_brute", "fish_05", seed=4)
    det_ok = a["damage"] == r_armed["damage"]
    print(f"\n[결정론] 동일 seed 재현 동일? {'예 ✅' if det_ok else '아니오 ❌'}")

    ok = atk_ok and def_ok and det_ok
    print("\n" + "=" * 64)
    print(f"종합: {'PASS ✅' if ok else 'FAIL ❌'}")
    print("=" * 64)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
