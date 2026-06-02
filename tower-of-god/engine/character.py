#!/usr/bin/env python3
"""캐릭터 생성·성장 도구 (character.py)

  create   대화형 캐릭터 생성 → save/player.json
  levelup  경험치로 레벨업 처리(스탯 증가, 해금 가능 스킬 안내)
  learn    조건 충족 시 스킬 습득

모든 쓰기는 '읽고-수정하고-쓰기'를 임시파일+원자적 교체(.bak 백업)로 안전하게 한다.
파생 수치(HP/신수)와 스탯 키는 resolve.py 와 공식을 공유한다.
규칙 근거: rules/progression.md
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R  # noqa: E402

STATS = ["근력", "민첩", "체력", "신수조작", "신수저항", "정신력"]

# ── 생성 규칙 ───────────────────────────────────────────────────────────────
BASE_STAT = 8            # 모든 스탯 시작값
CREATION_POOL = 12       # 생성 시 배분 포인트
CREATION_CAP = 18        # 생성 시 스탯 상한
STAT_PER_LEVEL = 3       # 레벨업당 배분 포인트(일반)
IRREGULAR_BONUS_POINT = 1  # 이레귤러 레벨업 추가 포인트
IRREGULAR_EXP_MULT = 1.20  # 이레귤러 경험치 획득 배수(참고용 메모)

# 포지션: 표시명 / 주력스탯(생성·성장 가중) / 시작스킬
POSITIONS = {
    "fisherman":       {"이름": "낚시꾼",   "주력": ["근력", "체력"],     "시작": ["fish_01", "fish_02", "fish_03"]},
    "spear_bearer":    {"이름": "창지기",   "주력": ["민첩", "근력"],     "시작": ["spear_01", "spear_02", "spear_03"]},
    "light_bearer":    {"이름": "등대지기", "주력": ["정신력", "신수조작"], "시작": ["light_01", "light_02", "light_03"]},
    "wave_controller": {"이름": "파도잡이", "주력": ["신수조작", "신수저항"], "시작": ["wave_01", "wave_02", "wave_03"]},
    "scout":           {"이름": "탐색꾼",   "주력": ["민첩", "정신력"],   "시작": ["scout_01", "scout_02", "scout_03"]},
    "anima":           {"이름": "애니마",   "주력": ["정신력", "신수조작"], "시작": ["anima_01", "anima_02", "anima_03"]},
}

# tier 별 습득 최소 레벨 (시작 스킬은 예외로 무조건 보유)
TIER_MIN_LEVEL = {1: 1, 2: 3, 3: 6, 4: 10, 5: 15}

DEFAULT_SAVE = os.path.join(R.BASE_DIR, "save", "player.json")


# ──────────────────────────────────────────────────────────────────────────
# 공식
# ──────────────────────────────────────────────────────────────────────────

def exp_to_next(level):
    """다음 레벨까지 필요한 경험치. 곡선: 60 * level^1.5 (rules/progression.md)."""
    return int(round(60 * (level ** 1.5)))


# ──────────────────────────────────────────────────────────────────────────
# 안전한 읽기/쓰기
# ──────────────────────────────────────────────────────────────────────────

def read_player(path):
    if not os.path.exists(path):
        raise SystemExit(_err(f"세이브가 없습니다: {path} (먼저 create 하세요)"))
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_player(path, data):
    """임시파일에 쓴 뒤 원자적 교체. 기존 파일은 .bak 로 백업."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if os.path.exists(path):
        bak = path + ".bak"
        with open(path, "r", encoding="utf-8") as src, \
                open(bak, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _err(msg):
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False, indent=2)


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def recompute_derived(player, heal_full=False):
    """스탯 변경 후 최대 HP/신수 재계산. heal_full 이면 가득 채움, 아니면 초과분만 보정."""
    s = player["스탯"]
    player["최대HP"] = R.derive_hp_max(s, player["레벨"])
    player["최대신수"] = R.derive_shinsu_max(s)
    if heal_full:
        player["HP"] = player["최대HP"]
        player["신수"] = player["최대신수"]
    else:
        player["HP"] = min(player.get("HP", player["최대HP"]), player["최대HP"])
        player["신수"] = min(player.get("신수", player["최대신수"]), player["최대신수"])


def new_player_template():
    return {
        "이름": "", "포지션": "", "이레귤러여부": False,
        "레벨": 1, "경험치": 0,
        "스탯": {k: BASE_STAT for k in STATS},
        "HP": 0, "최대HP": 0, "신수": 0, "최대신수": 0,
        "배운스킬": [], "인벤토리": [],
        "장비": {"무기": None, "방어구": None, "장신구": None},
        "돈": 50, "현재층": "f01",
        "랭킹": {"점수": 0, "등급": "무급", "순위": None},
        "관계": {}, "상태이상": [], "업적": [], "플레이로그_요약": [],
    }


# ──────────────────────────────────────────────────────────────────────────
# create — 대화형 캐릭터 생성
# ──────────────────────────────────────────────────────────────────────────

def cmd_create(args):
    path = args.actor or DEFAULT_SAVE
    if os.path.exists(path) and not args.force:
        raise SystemExit(_err(f"이미 세이브가 있습니다: {path} "
                              f"(덮어쓰려면 --force). 보통은 '이어하기'로 진행하세요."))

    interactive = sys.stdin.isatty() and not args.noninteractive
    p = new_player_template()

    # 이름 ----------------------------------------------------------------
    p["이름"] = args.name or (_ask("이름을 입력하세요: ") if interactive else "이름없는 도전자")

    # 포지션 --------------------------------------------------------------
    if args.position:
        pos = args.position
    elif interactive:
        print("\n[포지션 선택]")
        for i, (pid, info) in enumerate(POSITIONS.items(), 1):
            note = " (로 포 비아 혈통 전용)" if pid == "anima" else ""
            print(f"  {i}) {info['이름']} ({pid}){note} — 주력 {', '.join(info['주력'])}")
        pos = _choose_position()
    else:
        pos = "fisherman"
    if pos not in POSITIONS:
        raise SystemExit(_err(f"알 수 없는 포지션: {pos}"))

    # 이레귤러 / 일반 -----------------------------------------------------
    if args.irregular is not None:
        irregular = args.irregular
    elif interactive:
        ans = _ask("\n출신을 고르세요 — 1) 일반 도전자  2) 이레귤러(고위험 고성장): ")
        irregular = ans.strip() == "2"
    else:
        irregular = False

    # 애니마 혈통 제한 ----------------------------------------------------
    if pos == "anima" and not (irregular or args.allow_anima):
        raise SystemExit(_err("애니마는 로 포 비아 혈통만 선택할 수 있습니다 "
                              "(이레귤러이거나 --allow-anima 필요). 세계관 설정."))

    info = POSITIONS[pos]
    p["포지션"] = pos
    p["이레귤러여부"] = irregular

    # 포지션 보정: 주력 스탯 +2씩
    for st in info["주력"]:
        p["스탯"][st] += 2

    # 스탯 배분 ----------------------------------------------------------
    alloc = _allocate_stats(args, info, interactive)
    for st, v in alloc.items():
        p["스탯"][st] += v

    # 시작 스킬 / 파생 / 초기 기록 ----------------------------------------
    p["배운스킬"] = list(info["시작"])
    recompute_derived(p, heal_full=True)

    if irregular:
        p["업적"].append("이레귤러 — 선택받지 않은 자")
        p["플레이로그_요약"].append("이레귤러로서 탑에 강제로 진입했다. 모두가 경계한다.")
        # 이레귤러: 경계로 시작 평판/관계 불리
        p["랭킹"]["등급"] = "감시대상"
    else:
        p["플레이로그_요약"].append("정식 절차로 탑에 입장했다.")

    write_player(path, p)
    _emit({
        "ok": True, "command": "create", "saved": path,
        "요약": {
            "이름": p["이름"], "포지션": f"{info['이름']}({pos})",
            "이레귤러": irregular, "레벨": p["레벨"],
            "스탯": p["스탯"], "최대HP": p["최대HP"], "최대신수": p["최대신수"],
            "배운스킬": p["배운스킬"],
        },
        "다음": "engine/resolve.py 로 판정/전투를 진행하고, 경험치는 levelup 으로 반영하세요.",
    })


def _ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _choose_position():
    ids = list(POSITIONS.keys())
    while True:
        ans = _ask("번호 또는 영문 id 입력: ").strip()
        if ans in POSITIONS:
            return ans
        if ans.isdigit() and 1 <= int(ans) <= len(ids):
            return ids[int(ans) - 1]
        print("  올바른 번호/ id 를 입력하세요.")


def _allocate_stats(args, info, interactive):
    """CREATION_POOL 포인트를 배분. --stat 인자 우선, 없으면 대화형, 없으면 주력 자동배분."""
    alloc = {k: 0 for k in STATS}
    # 비대화형 --stat "근력=4,체력=3,..." 지원
    if args.stat:
        for chunk in args.stat.split(","):
            if "=" not in chunk:
                continue
            k, v = chunk.split("=")
            k, v = k.strip(), int(v)
            if k not in STATS:
                raise SystemExit(_err(f"알 수 없는 스탯: {k}"))
            alloc[k] += v
        _validate_alloc(alloc, info)
        return alloc

    if interactive:
        print(f"\n[스탯 배분] 총 {CREATION_POOL} 포인트. 기본 {BASE_STAT}, "
              f"주력 +2 적용됨. 스탯당 상한 {CREATION_CAP}.")
        remaining = CREATION_POOL
        for st in STATS:
            base = BASE_STAT + (2 if st in info["주력"] else 0)
            while True:
                raw = _ask(f"  {st} (현재 {base}, 남은 {remaining}) 에 더할 값[0~]: ")
                v = int(raw) if raw.isdigit() else 0
                if v > remaining:
                    print(f"    남은 포인트({remaining})를 초과했습니다.")
                    continue
                if base + v > CREATION_CAP:
                    print(f"    상한 {CREATION_CAP} 초과입니다.")
                    continue
                alloc[st] = v
                remaining -= v
                break
            if remaining == 0:
                break
        return alloc

    # 자동: 주력 스탯에 몰아주기
    primaries = info["주력"]
    per = CREATION_POOL // len(primaries)
    rem = CREATION_POOL - per * len(primaries)
    for i, st in enumerate(primaries):
        alloc[st] = per + (rem if i == 0 else 0)
    return alloc


def _validate_alloc(alloc, info):
    total = sum(alloc.values())
    if total > CREATION_POOL:
        raise SystemExit(_err(f"배분 합계 {total} 가 한도 {CREATION_POOL} 초과"))
    for st, v in alloc.items():
        base = BASE_STAT + (2 if st in info["주력"] else 0)
        if base + v > CREATION_CAP:
            raise SystemExit(_err(f"{st} 가 생성 상한 {CREATION_CAP} 초과"))


# ──────────────────────────────────────────────────────────────────────────
# levelup — 경험치로 레벨업
# ──────────────────────────────────────────────────────────────────────────

def cmd_levelup(args):
    path = args.actor or DEFAULT_SAVE
    p = read_player(path)
    if args.add_exp:
        p["경험치"] = p.get("경험치", 0) + args.add_exp

    info = POSITIONS.get(p["포지션"], {"주력": ["근력", "체력"]})
    gained = []
    while p["경험치"] >= exp_to_next(p["레벨"]):
        need = exp_to_next(p["레벨"])
        p["경험치"] -= need
        p["레벨"] += 1
        points = STAT_PER_LEVEL + (IRREGULAR_BONUS_POINT if p["이레귤러여부"] else 0)
        added = _auto_distribute(p, info["주력"], points)
        gained.append({"레벨": p["레벨"], "획득포인트": points, "분배": added})

    recompute_derived(p, heal_full=True)  # 레벨업 시 완전 회복
    unlockable = _unlockable_skills(p)
    write_player(path, p)
    _emit({
        "ok": True, "command": "levelup", "saved": path,
        "레벨": p["레벨"], "잔여경험치": p["경험치"],
        "다음레벨필요": exp_to_next(p["레벨"]),
        "레벨업내역": gained or "레벨업 없음(경험치 부족)",
        "스탯": p["스탯"], "최대HP": p["최대HP"], "최대신수": p["최대신수"],
        "습득가능스킬": unlockable,
    })


def _auto_distribute(player, primaries, points):
    """레벨업 포인트를 분배. 주력 스탯을 먼저 채우고 남으면 나머지에 라운드로빈."""
    added = {}
    order = primaries + [s for s in STATS if s not in primaries]
    for i in range(points):
        target = order[i % len(order)]
        player["스탯"][target] += 1
        added[target] = added.get(target, 0) + 1
    return added


# ──────────────────────────────────────────────────────────────────────────
# learn — 스킬 습득
# ──────────────────────────────────────────────────────────────────────────

def cmd_learn(args):
    path = args.actor or DEFAULT_SAVE
    p = read_player(path)
    skills = R.load_skills()
    sid = args.skill
    sk = skills.get(sid)
    if sk is None:
        raise SystemExit(_err(f"알 수 없는 스킬: {sid}"))
    if sid in p["배운스킬"]:
        raise SystemExit(_err(f"이미 배운 스킬: {sid}"))

    reasons = []
    # 포지션 일치 (이레귤러 + 사사(mentor) 시 타 포지션 허용)
    same_pos = sk["position"] == p["포지션"]
    if not same_pos:
        if p["이레귤러여부"] and args.mentor:
            reasons.append(f"타 포지션 스킬을 사사({args.mentor})로 습득 — 이레귤러 특성")
        else:
            raise SystemExit(_err(
                f"{sid} 는 {sk['position']} 포지션 스킬입니다. "
                f"(이레귤러가 --mentor NPC 로 사사할 때만 타 포지션 습득 가능)"))

    # 레벨 요구
    need_lv = TIER_MIN_LEVEL.get(sk["tier"], 1)
    if p["레벨"] < need_lv:
        raise SystemExit(_err(
            f"{sid} 는 tier {sk['tier']} — 레벨 {need_lv} 이상 필요(현재 {p['레벨']})."))

    # 고티어 사사 요구 (tier 4~5 는 사사 또는 강제 플래그 필요)
    if sk["tier"] >= 4 and not (args.mentor or args.force):
        raise SystemExit(_err(
            f"{sid} 는 tier {sk['tier']} 비전(秘傳)입니다. "
            f"--mentor NPC_id (사사) 가 필요합니다."))

    p["배운스킬"].append(sid)
    if args.mentor:
        p.setdefault("관계", {})
        p["관계"][args.mentor] = p["관계"].get(args.mentor, 0) + 5
        reasons.append(f"{args.mentor} 와의 유대 +5")
    write_player(path, p)
    _emit({
        "ok": True, "command": "learn", "saved": path,
        "습득": {"id": sid, "name": sk["name"], "tier": sk["tier"],
                "효과타입": sk["효과타입"]},
        "배운스킬": p["배운스킬"], "비고": reasons or "조건 충족",
    })


def _unlockable_skills(player):
    """현재 레벨/포지션에서 배울 수 있는(아직 미습득) 스킬 목록."""
    skills = R.load_skills()
    out = []
    for sid, sk in skills.items():
        if sid in player["배운스킬"]:
            continue
        if sk["position"] != player["포지션"]:
            continue
        if player["레벨"] < TIER_MIN_LEVEL.get(sk["tier"], 1):
            continue
        mentor = " (사사 필요)" if sk["tier"] >= 4 else ""
        out.append(f"{sid} {sk['name']} (tier {sk['tier']}){mentor}")
    return out


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="캐릭터 생성·성장 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="캐릭터 생성")
    c.add_argument("--actor", help="저장 경로(기본 save/player.json)")
    c.add_argument("--name")
    c.add_argument("--position", choices=list(POSITIONS.keys()))
    c.add_argument("--irregular", type=_bool, default=None,
                   help="true/false. 이레귤러 여부")
    c.add_argument("--stat", help='비대화형 배분 "근력=4,체력=3,..."')
    c.add_argument("--allow-anima", action="store_true",
                   help="애니마 혈통 제한 우회(GM 승인)")
    c.add_argument("--force", action="store_true", help="기존 세이브 덮어쓰기")
    c.add_argument("--noninteractive", action="store_true")
    c.set_defaults(func=cmd_create)

    lu = sub.add_parser("levelup", help="레벨업 처리")
    lu.add_argument("--actor", help="세이브 경로")
    lu.add_argument("--add-exp", type=int, default=0, help="경험치 추가 후 처리")
    lu.set_defaults(func=cmd_levelup)

    ln = sub.add_parser("learn", help="스킬 습득")
    ln.add_argument("--actor", help="세이브 경로")
    ln.add_argument("--skill", required=True)
    ln.add_argument("--mentor", help="사사한 NPC id(타 포지션/고티어 습득용)")
    ln.add_argument("--force", action="store_true", help="고티어 비전 강제 습득(GM 승인)")
    ln.set_defaults(func=cmd_learn)

    args = parser.parse_args(argv)
    args.func(args)


def _bool(v):
    return str(v).lower() in ("1", "true", "yes", "y", "참", "예")


if __name__ == "__main__":
    main()
