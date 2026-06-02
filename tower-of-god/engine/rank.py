#!/usr/bin/env python3
"""랭킹·명성 계산 엔진 (rank.py)

  recalc  player.json 의 랭킹 점수/등급/순위를 재계산해 기록
  show    계산 결과만 출력(쓰지 않음)
  board   랭커 명단(리더보드) 출력

점수 = 도달층 + 클리어 시험 등급 + 처치한 강적 + 완료 퀘스트 + 평판(명성/악명) 가중.
플레이어 점수를 data/rankers.json 명단 사이에 끼워 순위를 매긴다.
규칙 근거: rules/social.md, rules/progression.md
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R  # noqa: E402
import character as C  # noqa: E402  (안전한 읽기/쓰기 재사용)

# ── 점수 가중치 (튜닝 포인트) ──────────────────────────────────────────────
FLOOR_W = 120          # 도달 층 1당
GRADE_POINTS = {"대성공": 60, "성공": 35, "통과": 35, "실패": 0, "대실패": 0}
KILL_W = 1.5           # 처치한 적의 권장전투력 1당
QUEST_W = 40           # 완료 퀘스트 1당
FAME_W = 2.0           # 명성 1당
INFAMY_W = 1.2         # 악명 1당 (악명도 명망 점수엔 기여하되, 축은 social.md 참조)

# ── 등급 티어 (점수 하한, 이름) — 무명 → 랭커 ───────────────────────────────
TIERS = [
    (50000, "랭커"),
    (10000, "준랭커"),
    (4000, "정예"),
    (1500, "유망주"),
    (300, "정규등반자"),
    (0, "무명"),
]


def load_rankers():
    path = os.path.join(R.DATA_DIR, "rankers.json")
    return R._load_json(path)["rankers"]


def load_floor_numbers():
    path = os.path.join(R.DATA_DIR, "floors.json")
    floors = R._load_json(path)["floors"]
    return {f["id"]: f.get("floor", 0) for f in floors}


def best_floor_number(player, floor_no):
    ids = [player.get("현재층"), player.get("최고도달층")]
    nums = [floor_no.get(fid, 0) for fid in ids if fid]
    return max(nums) if nums else 0


def tier_for(score):
    for low, name in TIERS:
        if score >= low:
            return name
    return "무명"


def compute_score(player, floor_no, enemies):
    floor_n = best_floor_number(player, floor_no)
    floor_pts = floor_n * FLOOR_W

    # 클리어한 시험: [{"등급": "성공", ...}] 또는 ["성공", ...]
    test_pts = 0
    for t in player.get("클리어시험", []):
        grade = t.get("등급") if isinstance(t, dict) else t
        test_pts += GRADE_POINTS.get(grade, 0)

    # 처치한 강적: 적 id 목록 → 권장전투력 합 가중
    kill_raw = 0
    for eid in player.get("처치한강적", []):
        e = enemies.get(eid, {})
        kill_raw += e.get("권장전투력", 0)
    kill_pts = kill_raw * KILL_W

    quest_pts = len(player.get("완료퀘스트", [])) * QUEST_W

    fame = player.get("명성", 0)
    infamy = player.get("악명", 0)
    rep_pts = fame * FAME_W + infamy * INFAMY_W

    total = round(floor_pts + test_pts + kill_pts + quest_pts + rep_pts)
    return {
        "총점": total,
        "내역": {
            "도달층": {"층": floor_n, "점수": floor_pts},
            "시험": {"건수": len(player.get("클리어시험", [])), "점수": test_pts},
            "강적": {"전투력합": kill_raw, "점수": round(kill_pts)},
            "퀘스트": {"건수": len(player.get("완료퀘스트", [])), "점수": quest_pts},
            "평판": {"명성": fame, "악명": infamy, "점수": round(rep_pts)},
        },
    }


def place_on_board(score, rankers):
    """플레이어 점수를 명단 사이에 끼워 순위와 이웃을 구한다."""
    board = [{"name": r["name"], "점수": r["점수"], "티어": r.get("티어", "")}
             for r in rankers]
    board.append({"name": "▶ 당신", "점수": score, "티어": tier_for(score),
                  "_player": True})
    board.sort(key=lambda x: -x["점수"])
    idx = next(i for i, e in enumerate(board) if e.get("_player"))
    above = board[idx - 1] if idx > 0 else None
    below = board[idx + 1] if idx + 1 < len(board) else None
    return {
        "순위": idx + 1,
        "총원(명단+나)": len(board),
        "상위_랭커": _brief(above),
        "추격_대상(바로 아래)": _brief(below),
    }


def _brief(entry):
    if not entry:
        return None
    return {"이름": entry["name"], "점수": entry["점수"], "티어": entry["티어"]}


def evaluate(player):
    floor_no = load_floor_numbers()
    enemies = R.load_enemies()
    rankers = load_rankers()
    sc = compute_score(player, floor_no, enemies)
    tier = tier_for(sc["총점"])
    placement = place_on_board(sc["총점"], rankers)
    return {
        "점수": sc["총점"],
        "등급": tier,
        "순위": placement["순위"],
        "랭커권역": tier == "랭커",
        "점수_내역": sc["내역"],
        "리더보드_위치": placement,
    }


# ──────────────────────────────────────────────────────────────────────────
# 명령
# ──────────────────────────────────────────────────────────────────────────

def cmd_recalc(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    result = evaluate(player)

    prev = player.get("랭킹", {}) or {}
    prev_tier = prev.get("등급")
    player["랭킹"] = {
        "점수": result["점수"],
        "등급": result["등급"],
        "순위": result["순위"],
    }
    C.write_player(path, player)

    tier_changed = prev_tier is not None and prev_tier != result["등급"]
    C._emit({
        "ok": True, "command": "recalc", "saved": path,
        "이전등급": prev_tier, "현재등급": result["등급"],
        "티어변동": tier_changed,
        "랭커권역_진입": result["랭커권역"],
        **result,
        "GM메모": ("티어가 바뀌었습니다 — 연출을 넣으세요." if tier_changed
                 else "티어 변동 없음"),
    })


def cmd_show(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    C._emit({"ok": True, "command": "show", **evaluate(player)})


def cmd_board(args):
    rankers = load_rankers()
    board = sorted(rankers, key=lambda r: -r["점수"])
    C._emit({
        "ok": True, "command": "board",
        "랭커명단": [{"순위": i + 1, "이름": r["name"], "역할": r.get("역할"),
                  "티어": r.get("티어"), "점수": r["점수"]}
                 for i, r in enumerate(board)],
        "등급기준": [{"하한점수": low, "등급": name} for low, name in TIERS],
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description="랭킹·명성 계산 엔진")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("recalc", help="player.json 랭킹 갱신")
    r.add_argument("--actor", help="세이브 경로(기본 save/player.json)")
    r.set_defaults(func=cmd_recalc)

    s = sub.add_parser("show", help="계산 결과만 출력")
    s.add_argument("--actor", help="세이브 경로")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("board", help="랭커 명단 출력")
    b.set_defaults(func=cmd_board)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
