#!/usr/bin/env python3
"""세이브 무결성 검증 (validate.py)

  python3 engine/validate.py save/player.json

player.json 의 스키마·정합성·치트 의심을 검사한다.
  - 오류(error): 진행을 막아야 하는 문제(필드 누락, 음수 HP, 스탯 이상치, 파생값 불일치,
    인벤토리-장비 불일치, 치트 의심 등)
  - 경고(warning): 진행은 가능하나 점검이 필요한 사항

오류가 있으면 종료코드 1 과 함께 마지막 정상 백업을 제안한다.
규칙 근거: rules/progression.md, rules/economy.md
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R       # noqa: E402
import character as C     # noqa: E402
import save as SAVE       # noqa: E402

STATS = ["근력", "민첩", "체력", "신수조작", "신수저항", "정신력"]
REQUIRED = ["이름", "포지션", "레벨", "경험치", "스탯", "HP", "최대HP",
            "신수", "최대신수", "배운스킬", "인벤토리", "장비", "돈", "현재층"]
SLOT_KIND = {"무기": "무기", "방어구": "방어구", "장신구": "장신구"}


def validate_player(player):
    errors, warnings = [], []

    # 1) 필수 필드 ------------------------------------------------------
    for f in REQUIRED:
        if f not in player:
            errors.append(f"필수 필드 누락: {f}")
    if errors:  # 핵심 필드가 없으면 이후 검사 불가
        return errors, warnings

    stats = player["스탯"]
    level = player["레벨"]
    irregular = player.get("이레귤러여부", False)

    # 2) 스탯 존재/범위 -------------------------------------------------
    for s in STATS:
        if s not in stats:
            errors.append(f"스탯 누락: {s}")
        elif not isinstance(stats[s], int) or stats[s] < 1:
            errors.append(f"스탯 이상치(<1 또는 비정수): {s}={stats.get(s)}")

    # 3) HP/신수 정합 ---------------------------------------------------
    if player["HP"] < 0:
        errors.append(f"음수 HP: {player['HP']}")
    if player["HP"] > player["최대HP"]:
        errors.append(f"HP가 최대HP 초과: {player['HP']}/{player['최대HP']}")
    if player["신수"] < 0:
        errors.append(f"음수 신수: {player['신수']}")
    if player["신수"] > player["최대신수"]:
        errors.append(f"신수가 최대신수 초과: {player['신수']}/{player['최대신수']}")

    # 4) 파생값 공식 일치 (기본 스탯 기준; 장비 보정은 런타임에만 적용) ----
    if all(s in stats for s in STATS):
        exp_hp = R.derive_hp_max(stats, level)
        exp_sp = R.derive_shinsu_max(stats)
        if player["최대HP"] != exp_hp:
            errors.append(f"최대HP 불일치: 저장 {player['최대HP']} ≠ 공식 {exp_hp} "
                          f"(스탯/레벨 변조 의심)")
        if player["최대신수"] != exp_sp:
            errors.append(f"최대신수 불일치: 저장 {player['최대신수']} ≠ 공식 {exp_sp}")

    # 5) 치트 의심: 스탯 총합 vs 레벨 기대치 -----------------------------
    per = C.STAT_PER_LEVEL + (C.IRREGULAR_BONUS_POINT if irregular else 0)
    expected_total = (C.BASE_STAT * 6) + 4 + C.CREATION_POOL + max(0, level - 1) * per
    actual_total = sum(stats.get(s, 0) for s in STATS)
    if actual_total > expected_total:
        errors.append(f"스탯 총합 과다(치트 의심): 합계 {actual_total} > 기대 {expected_total} "
                      f"(레벨 {level}, 이레귤러 {irregular})")
    elif actual_total < expected_total:
        warnings.append(f"스탯 총합 미달: 합계 {actual_total} < 기대 {expected_total} "
                        f"(미분배 포인트?)")
    # 개별 스탯 상한(관대한 휴리스틱)
    cap = C.CREATION_CAP + max(0, level - 1) * per + 4
    for s in STATS:
        if stats.get(s, 0) > cap:
            errors.append(f"단일 스탯 과다(치트 의심): {s}={stats[s]} > 상한 {cap}")

    # 6) 레벨/경험치 ----------------------------------------------------
    if player["레벨"] < 1:
        errors.append(f"레벨 이상치: {player['레벨']}")
    if player["경험치"] < 0:
        errors.append(f"음수 경험치: {player['경험치']}")
    else:
        need = C.exp_to_next(level)
        if player["경험치"] >= need:
            warnings.append(f"경험치가 레벨업 임계 도달: {player['경험치']}/{need} "
                            f"(levelup 필요)")

    # 7) 돈/평판 --------------------------------------------------------
    if player.get("돈", 0) < 0:
        errors.append(f"음수 돈: {player['돈']}")
    for k in ("명성", "악명"):
        if player.get(k, 0) < 0:
            errors.append(f"음수 {k}: {player[k]}")

    # 8) 인벤토리-장비 정합 ---------------------------------------------
    items = _safe_items()
    inv = player.get("인벤토리", [])
    if not isinstance(inv, list):
        errors.append("인벤토리가 리스트가 아님")
    else:
        for e in inv:
            iid = e.get("id")
            if items is not None and iid not in items:
                errors.append(f"인벤토리에 알 수 없는 아이템 id: {iid}")
            if e.get("수량", 0) <= 0:
                errors.append(f"인벤토리 수량 이상: {iid}={e.get('수량')}")

    gear = player.get("장비", {})
    if not isinstance(gear, dict):
        errors.append("장비가 딕셔너리가 아님")
    else:
        for slot, item in gear.items():
            if item is None:
                continue
            if not isinstance(item, dict):
                errors.append(f"장비 슬롯 {slot} 형식 오류")
                continue
            if items is not None and item.get("id") not in items:
                errors.append(f"장비에 알 수 없는 아이템 id: {item.get('id')}")
            kind = item.get("종류")
            if slot in SLOT_KIND and kind and SLOT_KIND[slot] != kind:
                errors.append(f"장비 슬롯-종류 불일치: {slot} 슬롯에 {kind}")

    # 9) 포지션/스킬 ----------------------------------------------------
    if player["포지션"] not in C.POSITIONS:
        errors.append(f"알 수 없는 포지션: {player['포지션']}")
    skills = _safe_skills()
    if skills is not None:
        for sid in player.get("배운스킬", []):
            if sid not in skills:
                errors.append(f"알 수 없는 스킬 id: {sid}")

    return errors, warnings


def _safe_items():
    try:
        return R._load_json(os.path.join(R.DATA_DIR, "items.json"))["items"]
    except Exception:
        return None


def _safe_skills():
    try:
        return R.load_skills()
    except Exception:
        return None


def suggest_backup():
    snaps = SAVE.list_snapshots(SAVE.DEFAULT_BACKUPS)
    if not snaps:
        return None
    last = snaps[-1]
    return {"스냅id": last["스냅id"], "시각": last["시각"],
            "복원명령": f"python3 engine/save.py load --id {last['스냅id']}"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "사용법: validate.py <player.json 경로>"},
                         ensure_ascii=False, indent=2))
        sys.exit(2)
    path = sys.argv[1]

    # JSON 파싱 자체가 깨졌는지 ------------------------------------------
    try:
        with open(path, "r", encoding="utf-8") as fh:
            player = json.load(fh)
    except FileNotFoundError:
        print(json.dumps({"ok": False, "치명": f"파일 없음: {path}"},
                         ensure_ascii=False, indent=2))
        sys.exit(1)
    except json.JSONDecodeError as e:
        result = {"ok": False, "치명": f"JSON 파싱 실패(파일 손상): {e}",
                  "제안_백업": suggest_backup(),
                  "조치": "이 세이브는 손상되었습니다. 백업을 복원하세요."}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    errors, warnings = validate_player(player)
    ok = len(errors) == 0
    result = {
        "ok": ok, "검증대상": path,
        "오류": errors, "경고": warnings,
        "요약": f"오류 {len(errors)}건, 경고 {len(warnings)}건",
    }
    if not ok:
        result["제안_백업"] = suggest_backup()
        result["조치"] = ("검증 실패: 진행을 중단하고 사용자에게 알리세요. "
                        "필요 시 마지막 정상 백업을 복원하세요.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
