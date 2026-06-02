#!/usr/bin/env python3
"""퀘스트·스토리 엔진 (quest.py)

  start     퀘스트 시작 → world_state.json 에 진행중으로 기록
  advance   퀘스트 단계/분기 진행 기록
  complete  퀘스트 완료 → 보상·분기 결과를 player.json/world_state.json 에 반영
  trigger   현재 층/조건에 맞는 랜덤 이벤트 추첨(resolve.py 난수 사용)

분기 선택의 결과(평판/관계/세계변화)는 world_state.json 에 영구 기록되어
이후 턴에 GM이 읽어 일관성을 유지한다.
데이터: data/quests.json, data/events.json. 규칙 근거: rules/story.md
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R       # noqa: E402
import character as C     # noqa: E402

DEFAULT_WORLD = os.path.join(R.BASE_DIR, "save", "world_state.json")


# ── 데이터 로딩 ─────────────────────────────────────────────────────────────

def load_quests():
    return R._load_json(os.path.join(R.DATA_DIR, "quests.json"))["quests"]


def load_events():
    return R._load_json(os.path.join(R.DATA_DIR, "events.json"))["events"]


def load_floor_meta():
    floors = R._load_json(os.path.join(R.DATA_DIR, "floors.json"))["floors"]
    return {f["id"]: {"floor": f.get("floor", 0), "kind": f.get("kind", "")}
            for f in floors}


def load_items():
    return R._load_json(os.path.join(R.DATA_DIR, "items.json"))["items"]


def read_world(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    # 없으면 기본 골격 생성
    return {
        "현재층": "f01", "시간": {"턴": 0, "주기": "낮"},
        "퀘스트상태": {}, "진행중퀘스트": [], "완료퀘스트": [], "실패퀘스트": [],
        "죽은NPC": [], "배신한NPC": [], "동맹NPC": [],
        "세력관계변화": {}, "개방된지역": [], "봉쇄된지역": [],
        "월드플래그": {}, "발생이벤트로그": [],
    }


# ── 세계 변화 적용(일반화) ───────────────────────────────────────────────────

def apply_world_changes(world, changes):
    for k, v in (changes or {}).items():
        if isinstance(v, list):
            cur = world.setdefault(k, [])
            for x in v:
                if x not in cur:
                    cur.append(x)
        elif isinstance(v, dict):
            if k == "세력관계변화":
                tgt = world.setdefault(k, {})
                for fac, d in v.items():
                    tgt[fac] = tgt.get(fac, 0) + d
            else:  # 월드플래그 등
                world.setdefault(k, {}).update(v)
        else:
            world[k] = v


def apply_rewards(player, reward, items):
    player["경험치"] = player.get("경험치", 0) + reward.get("경험치", 0)
    player["돈"] = player.get("돈", 0) + reward.get("돈", 0)
    player["명성"] = player.get("명성", 0) + reward.get("명성", 0)
    player["악명"] = player.get("악명", 0) + reward.get("악명", 0)
    gained = []
    for iid in reward.get("아이템", []):
        it = items.get(iid)
        if not it:
            continue
        inv = player.setdefault("인벤토리", [])
        entry = next((e for e in inv if e.get("id") == iid), None)
        if entry:
            entry["수량"] = entry.get("수량", 1) + 1
        else:
            inv.append({"id": iid, "이름": it["이름"], "종류": it["종류"], "수량": 1})
        gained.append(it["이름"])
    return gained


def apply_branch(player, world, result):
    """분기 결과: 관계/명성/악명/세력/월드변화 적용."""
    for npc, d in (result.get("관계") or {}).items():
        rels = player.setdefault("관계", {})
        rels[npc] = max(-100, min(100, rels.get(npc, 0) + d))
    player["명성"] = player.get("명성", 0) + result.get("명성", 0)
    player["악명"] = player.get("악명", 0) + result.get("악명", 0)
    if result.get("세력관계변화"):
        apply_world_changes(world, {"세력관계변화": result["세력관계변화"]})
    apply_world_changes(world, result.get("월드변화") or {})


# ──────────────────────────────────────────────────────────────────────────
# start / advance / complete
# ──────────────────────────────────────────────────────────────────────────

def cmd_start(args):
    wpath = args.world or DEFAULT_WORLD
    world = read_world(wpath)
    quests = load_quests()
    q = quests.get(args.quest)
    if q is None:
        raise SystemExit(C._err(f"알 수 없는 퀘스트: {args.quest}"))
    if args.quest in world.get("완료퀘스트", []):
        raise SystemExit(C._err(f"이미 완료한 퀘스트: {args.quest}"))
    if args.quest in world.get("진행중퀘스트", []):
        raise SystemExit(C._err(f"이미 진행 중: {args.quest}"))

    # 선행 퀘스트 확인(경고 수준, --force 로 무시 가능)
    선행 = q.get("발동조건", {}).get("선행", [])
    미충족 = [p for p in 선행 if p not in world.get("완료퀘스트", [])]
    if 미충족 and not args.force:
        raise SystemExit(C._err(f"선행 퀘스트 미완료: {미충족} (--force 로 강제 시작 가능)"))

    world.setdefault("진행중퀘스트", []).append(args.quest)
    world.setdefault("퀘스트상태", {})[args.quest] = {"단계": 0, "분기": None}
    C.write_player(wpath, world)
    C._emit({"ok": True, "command": "start", "saved": wpath,
             "퀘스트": args.quest, "종류": q["종류"],
             "목표": q.get("목표", []), "관련NPC": q.get("관련NPC", []),
             "분기있음": bool(q.get("분기"))})


def cmd_advance(args):
    wpath = args.world or DEFAULT_WORLD
    world = read_world(wpath)
    if args.quest not in world.get("진행중퀘스트", []):
        raise SystemExit(C._err(f"진행 중이 아닌 퀘스트: {args.quest} (먼저 start)"))
    st = world.setdefault("퀘스트상태", {}).setdefault(args.quest, {"단계": 0, "분기": None})
    if args.step is not None:
        st["단계"] = args.step
    if args.branch is not None:
        st["분기"] = args.branch
    C.write_player(wpath, world)
    C._emit({"ok": True, "command": "advance", "saved": wpath,
             "퀘스트": args.quest, "상태": st})


def cmd_complete(args):
    wpath = args.world or DEFAULT_WORLD
    ppath = args.actor or C.DEFAULT_SAVE
    world = read_world(wpath)
    player = C.read_player(ppath)
    quests = load_quests()
    items = load_items()
    q = quests.get(args.quest)
    if q is None:
        raise SystemExit(C._err(f"알 수 없는 퀘스트: {args.quest}"))

    branch = args.branch or world.get("퀘스트상태", {}).get(args.quest, {}).get("분기")
    branch_obj = None
    if q.get("분기"):
        branch_obj = next((b for b in q["분기"] if b["id"] == branch), None)
        if branch_obj is None and not args.force:
            ids = [b["id"] for b in q["분기"]]
            raise SystemExit(C._err(
                f"분기 선택 필요: --branch 중 하나 {ids} (또는 --force)"))

    # 보상
    gained = apply_rewards(player, q.get("보상", {}), items)
    # 분기 결과
    branch_applied = None
    if branch_obj:
        apply_branch(player, world, branch_obj.get("결과", {}))
        branch_applied = branch_obj["id"]
    # 완료 시 세계변화
    apply_world_changes(world, q.get("결과에따른_세계변화", {}).get("완료시", {}))

    # 진행 상태 갱신
    if args.quest in world.get("진행중퀘스트", []):
        world["진행중퀘스트"].remove(args.quest)
    if args.quest not in world.setdefault("완료퀘스트", []):
        world["완료퀘스트"].append(args.quest)
    world.get("퀘스트상태", {}).pop(args.quest, None)
    # 플레이어 쪽 완료 기록(rank.py 점수 반영)
    if args.quest not in player.setdefault("완료퀘스트", []):
        player["완료퀘스트"].append(args.quest)
    player.setdefault("플레이로그_요약", []).append(
        f"퀘스트 '{args.quest}' 완료" + (f" (분기:{branch_applied})" if branch_applied else ""))

    C.write_player(ppath, player)
    C.write_player(wpath, world)
    C._emit({"ok": True, "command": "complete",
             "player_saved": ppath, "world_saved": wpath,
             "퀘스트": args.quest, "분기": branch_applied,
             "획득아이템": gained, "보상": q.get("보상", {}),
             "현재_명성": player.get("명성"), "현재_악명": player.get("악명"),
             "메모": "보상 경험치 반영 후 character.py levelup, rank.py recalc 를 호출하세요."})


# ──────────────────────────────────────────────────────────────────────────
# trigger — 랜덤 이벤트 추첨
# ──────────────────────────────────────────────────────────────────────────

def cmd_trigger(args):
    wpath = args.world or DEFAULT_WORLD
    world = read_world(wpath)
    events = load_events()
    fmeta = load_floor_meta()

    floor_id = args.floor or world.get("현재층", "f01")
    fmeta_cur = fmeta.get(floor_id, {"floor": 0, "kind": ""})
    fn = fmeta_cur["floor"]
    kind = fmeta_cur["kind"]

    pool = []
    for ev in events:
        c = ev.get("발동조건", {})
        if fn < c.get("최소층번호", 0):
            continue
        if fn > c.get("최대층번호", 9999):
            continue
        if c.get("kind") and kind not in c["kind"]:
            continue
        pool.append(ev)
    if not pool:
        C._emit({"ok": True, "command": "trigger", "층": floor_id,
                 "결과": "조건에 맞는 이벤트 없음"})
        return

    rng = R.RNG(seed=args.seed)
    weights = [ev.get("가중치", 1) for ev in pool]
    pick = _weighted_choice(rng, pool, weights)

    if args.record:
        world.setdefault("발생이벤트로그", []).append(
            {"층": floor_id, "이벤트": pick["id"]})
        C.write_player(wpath, world)

    C._emit({"ok": True, "command": "trigger", "층": floor_id, "층kind": kind,
             "후보수": len(pool), "기록": bool(args.record),
             "이벤트": {
                 "id": pick["id"], "종류": pick["종류"], "설명": pick["설명"],
                 "선택지": [{"id": o["id"], **({"판정": o["판정"]} if "판정" in o else {})}
                          for o in pick.get("선택지", [])],
                 "자동효과": pick.get("효과", {}),
             },
             "메모": "선택지 결과/효과는 GM이 resolve·inventory·rank·social 로 반영하고, "
                   "중요한 변화는 quest.py 또는 직접 world_state.json 에 기록하세요."})


def _weighted_choice(rng, items, weights):
    total = sum(weights)
    r = rng.r.uniform(0, total)
    upto = 0
    for it, w in zip(items, weights):
        upto += w
        if r <= upto:
            return it
    return items[-1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="퀘스트·스토리 엔진")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start", help="퀘스트 시작")
    s.add_argument("--quest", required=True)
    s.add_argument("--world")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_start)

    a = sub.add_parser("advance", help="퀘스트 단계/분기 진행")
    a.add_argument("--quest", required=True)
    a.add_argument("--world")
    a.add_argument("--step", type=int, default=None)
    a.add_argument("--branch", default=None)
    a.set_defaults(func=cmd_advance)

    c = sub.add_parser("complete", help="퀘스트 완료(보상·분기 반영)")
    c.add_argument("--quest", required=True)
    c.add_argument("--actor")
    c.add_argument("--world")
    c.add_argument("--branch", default=None)
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_complete)

    t = sub.add_parser("trigger", help="랜덤 이벤트 추첨")
    t.add_argument("--floor", help="층 id(기본 world_state 현재층)")
    t.add_argument("--world")
    t.add_argument("--seed", type=int, default=None)
    t.add_argument("--record", action="store_true", help="발생 이벤트를 world_state 에 기록")
    t.set_defaults(func=cmd_trigger)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
