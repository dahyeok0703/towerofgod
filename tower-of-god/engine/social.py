#!/usr/bin/env python3
"""NPC 관계·동료·세력 평판 도구 (social.py)

  relation  특정 NPC 호감도 조회/증감 (player.json 의 관계 필드 갱신)
  recruit   조건 충족 시 동료 영입 → 동료 액터를 만들어 전투(resolve.py)에 합류
  faction   세력 평판 조회/증감

강함 격차 규칙: 랭커·공주급 정전 인물은 초반에 정상적으로 싸워 이길 수 없다(현실적 권력 차).
규칙 근거: rules/social.md
모든 쓰기는 character.py 의 안전한 read-modify-write 를 재사용한다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R       # noqa: E402
import character as C     # noqa: E402

# ── 규칙 상수 ───────────────────────────────────────────────────────────────
RECRUIT_THRESHOLD = 50      # 동료 영입 최소 호감도
FRIEND_THRESHOLD = 30       # 우호
HOSTILE_THRESHOLD = -30     # 적대
TRUST_THRESHOLD = 70        # 깊은 신뢰(사사·비밀 개방)

# 강함 등급 → 정상적으로 상대하려면 필요한 최소 플레이어 레벨(현실적 권력 차)
POWER_MIN_LEVEL = {
    "일반": 1, "유망주": 3, "정예": 5, "준랭커": 20,
    "랭커": 40, "최상위랭커": 60, "전설": 100, "초월": 999,
}

# 강함 등급 → 동료 스탯 기준치
COMPANION_BASE_STAT = {
    "일반": 9, "유망주": 11, "정예": 13, "준랭커": 18,
    "랭커": 24, "최상위랭커": 30, "전설": 36, "초월": 44,
}

ALLY_DIR = os.path.join(R.BASE_DIR, "save", "allies")


def load_npcs():
    return R._load_json(os.path.join(R.DATA_DIR, "npcs.json"))["npcs"]


def load_factions():
    return R._load_json(os.path.join(R.DATA_DIR, "factions.json"))["factions"]


def _rel_label(score):
    if score >= TRUST_THRESHOLD:
        return "깊은 신뢰"
    if score >= RECRUIT_THRESHOLD:
        return "동료 가능"
    if score >= FRIEND_THRESHOLD:
        return "우호"
    if score <= HOSTILE_THRESHOLD:
        return "적대"
    return "중립"


def _power_note(npc, player_level):
    grade = npc.get("정전_강함_등급", "일반")
    need = POWER_MIN_LEVEL.get(grade, 1)
    beatable = player_level >= need
    return {
        "강함등급": grade, "정상교전_필요레벨": need,
        "현재_정상교전_가능": beatable,
        "비고": ("정상적으로 상대할 수 있다." if beatable
               else "현재 실력으론 정면으로 이길 수 없다. 도망·기지·성장이 필요하다."),
    }


# ──────────────────────────────────────────────────────────────────────────
# relation
# ──────────────────────────────────────────────────────────────────────────

def cmd_relation(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    npcs = load_npcs()
    npc = npcs.get(args.npc)
    if npc is None:
        raise SystemExit(C._err(f"알 수 없는 NPC: {args.npc}"))

    rels = player.setdefault("관계", {})
    if args.npc not in rels:
        rels[args.npc] = npc.get("플레이어와의_초기관계", {}).get("초기호감도", 0)

    changed = False
    before = rels[args.npc]
    if args.delta is not None:
        rels[args.npc] = max(-100, min(100, before + args.delta))
        changed = True
        C.write_player(path, player)

    after = rels[args.npc]
    C._emit({
        "ok": True, "command": "relation", "saved": path if changed else None,
        "npc": args.npc, "이름": npc["이름"],
        "역할": npc.get("플레이어와의_초기관계", {}).get("역할"),
        "호감도": after, "변화": (after - before) if changed else 0,
        "관계": _rel_label(after),
        "영입가능": npc.get("동료가능여부", False) and after >= RECRUIT_THRESHOLD,
        "권력차": _power_note(npc, player.get("레벨", 1)),
    })


# ──────────────────────────────────────────────────────────────────────────
# recruit
# ──────────────────────────────────────────────────────────────────────────

def cmd_recruit(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    npcs = load_npcs()
    npc = npcs.get(args.npc)
    if npc is None:
        raise SystemExit(C._err(f"알 수 없는 NPC: {args.npc}"))

    if not npc.get("동료가능여부", False):
        raise SystemExit(C._err(
            f"{npc['이름']} 은(는) 동료로 삼을 수 없는 인물입니다 "
            f"(강함등급 {npc.get('정전_강함_등급')}). 멘토/적/상인 등 다른 관계로 다뤄집니다."))

    favor = player.get("관계", {}).get(
        args.npc, npc.get("플레이어와의_초기관계", {}).get("초기호감도", 0))
    if favor < RECRUIT_THRESHOLD and not args.force:
        raise SystemExit(C._err(
            f"호감도 부족: 현재 {favor}, 영입엔 {RECRUIT_THRESHOLD} 필요. "
            f"relation 으로 호감도를 쌓으세요."))

    party = player.setdefault("동료", [])
    if any(c.get("id") == args.npc for c in party):
        raise SystemExit(C._err(f"이미 동료입니다: {npc['이름']}"))

    level = args.level or player.get("레벨", 1)
    actor = build_companion(args.npc, npc, level)
    os.makedirs(ALLY_DIR, exist_ok=True)
    ref = os.path.join(ALLY_DIR, f"{args.npc}.json")
    with open(ref, "w", encoding="utf-8") as fh:
        json.dump(actor, fh, ensure_ascii=False, indent=2)

    party.append({"id": args.npc, "이름": npc["이름"], "포지션": npc["포지션"],
                  "ref": os.path.relpath(ref, R.BASE_DIR), "레벨": level})
    player.setdefault("플레이로그_요약", []).append(f"{npc['이름']} 을(를) 동료로 맞았다.")
    C.write_player(path, player)
    C._emit({
        "ok": True, "command": "recruit", "saved": path,
        "동료": {"id": args.npc, "이름": npc["이름"], "포지션": npc["포지션"],
               "레벨": level, "actor_ref": party[-1]["ref"]},
        "전투합류": (f"resolve.py combat --mode start ... --allies {party[-1]['ref']} "
                 f"로 전투에 합류합니다."),
        "현재동료수": len(party),
    })


def build_companion(npc_id, npc, level):
    """NPC 데이터로 전투용 동료 액터 블록 생성 (resolve.py 가 읽는 내부 키)."""
    pos = npc["포지션"]
    grade = npc.get("정전_강함_등급", "일반")
    base = COMPANION_BASE_STAT.get(grade, 9)
    primaries = C.POSITIONS.get(pos, {"주력": ["근력", "체력"]})["주력"]
    stats = {k: base for k in C.STATS}
    for st in primaries:
        stats[st] += 3
    # 레벨 보정(완만)
    bump = max(0, (level - 1) // 2)
    for st in primaries:
        stats[st] += bump

    skills = list(C.POSITIONS.get(pos, {}).get("시작", []))
    for s in npc.get("사사가능스킬", []):
        if s not in skills:
            skills.append(s)

    actor = {
        "name": npc["이름"], "position": pos, "level": level,
        "stats": stats, "skills": skills, "status": [],
        "id": npc_id, "동료": True,
    }
    return R._ensure_actor(actor)


# ──────────────────────────────────────────────────────────────────────────
# faction
# ──────────────────────────────────────────────────────────────────────────

def cmd_faction(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    factions = load_factions()
    rep = player.setdefault("세력평판", {})

    if args.list or not args.faction:
        C._emit({
            "ok": True, "command": "faction", "세력평판": rep,
            "세력목록": {fid: f["이름"] for fid, f in factions.items()},
        })
        return

    if args.faction not in factions:
        raise SystemExit(C._err(f"알 수 없는 세력: {args.faction}"))
    rep.setdefault(args.faction, 0)
    before = rep[args.faction]
    changed = False
    if args.delta is not None:
        rep[args.faction] = max(-100, min(100, before + args.delta))
        changed = True
        C.write_player(path, player)
    fac = factions[args.faction]
    C._emit({
        "ok": True, "command": "faction", "saved": path if changed else None,
        "세력": args.faction, "이름": fac["이름"],
        "평판": rep[args.faction], "변화": (rep[args.faction] - before) if changed else 0,
        "우호세력": fac.get("우호세력", []), "적대세력": fac.get("적대세력", []),
        "가입혜택": fac.get("가입혜택"),
    })


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="NPC 관계·동료·세력 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("relation", help="NPC 호감도 조회/증감")
    r.add_argument("--actor")
    r.add_argument("--npc", required=True)
    r.add_argument("--delta", type=int, default=None, help="증감값(생략 시 조회만)")
    r.set_defaults(func=cmd_relation)

    rc = sub.add_parser("recruit", help="동료 영입")
    rc.add_argument("--actor")
    rc.add_argument("--npc", required=True)
    rc.add_argument("--level", type=int, default=None, help="동료 레벨(기본 플레이어 레벨)")
    rc.add_argument("--force", action="store_true", help="호감도 미달 강제 영입(GM 승인)")
    rc.set_defaults(func=cmd_recruit)

    f = sub.add_parser("faction", help="세력 평판 조회/증감")
    f.add_argument("--actor")
    f.add_argument("--faction")
    f.add_argument("--delta", type=int, default=None)
    f.add_argument("--list", action="store_true")
    f.set_defaults(func=cmd_faction)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
