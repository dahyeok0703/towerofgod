#!/usr/bin/env python3
"""인벤토리·장비·경제 도구 (inventory.py)

  add / remove        인벤토리 아이템 추가/제거
  equip / unequip     장비 착용/해제 (스탯보정·효과가 전투에 반영됨)
  use                 소모품 사용 (HP/신수 회복, 상태이상 해제)
  buy / sell          거점층 상점 거래 (가격은 평판에 영향받음)

데이터: data/items.json. 쓰기는 character.py 의 안전한 read-modify-write 재사용.
장비 슬롯의 스탯보정·효과는 engine/resolve.py 가 전투 계산에 반영한다.
규칙 근거: rules/economy.md
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R       # noqa: E402
import character as C     # noqa: E402

SLOT_BY_KIND = {"무기": "무기", "방어구": "방어구", "장신구": "장신구"}
SELL_RATE = 0.4           # 판매가 = 가격 × 이 비율 × 평판배수


def load_items():
    return R._load_json(os.path.join(R.DATA_DIR, "items.json"))["items"]


def get_item(items, item_id):
    it = items.get(item_id)
    if it is None:
        raise SystemExit(C._err(f"알 수 없는 아이템: {item_id}"))
    return it


def price_mult(player):
    """평판(명성/악명)에 따른 구매가 배수. 명성↑ 할인, 악명↑ 할증."""
    fame = player.get("명성", 0)
    infamy = player.get("악명", 0)
    return max(0.7, min(1.3, 1 - fame * 0.001 + infamy * 0.0005))


# ── 인벤토리 조작 헬퍼 ──────────────────────────────────────────────────────

def _find(inv, item_id):
    return next((e for e in inv if e.get("id") == item_id), None)


def _add(player, items, item_id, qty):
    it = get_item(items, item_id)
    inv = player.setdefault("인벤토리", [])
    entry = _find(inv, item_id)
    if entry:
        entry["수량"] = entry.get("수량", 1) + qty
    else:
        inv.append({"id": item_id, "이름": it["이름"], "종류": it["종류"], "수량": qty})
    return it


def _remove(player, item_id, qty):
    inv = player.setdefault("인벤토리", [])
    entry = _find(inv, item_id)
    if not entry or entry.get("수량", 0) < qty:
        have = entry.get("수량", 0) if entry else 0
        raise SystemExit(C._err(f"수량 부족: {item_id} (보유 {have}, 필요 {qty})"))
    entry["수량"] -= qty
    if entry["수량"] <= 0:
        inv.remove(entry)


# ──────────────────────────────────────────────────────────────────────────
# 명령
# ──────────────────────────────────────────────────────────────────────────

def cmd_add(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    it = _add(player, items, args.item, args.qty)
    C.write_player(path, player)
    C._emit({"ok": True, "command": "add", "saved": path,
             "추가": {"id": args.item, "이름": it["이름"], "수량": args.qty},
             "인벤토리": player["인벤토리"]})


def cmd_remove(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    _remove(player, args.item, args.qty)
    C.write_player(path, player)
    C._emit({"ok": True, "command": "remove", "saved": path,
             "제거": {"id": args.item, "수량": args.qty},
             "인벤토리": player["인벤토리"]})


def cmd_equip(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    it = get_item(items, args.item)
    slot = SLOT_BY_KIND.get(it["종류"])
    if slot is None:
        raise SystemExit(C._err(f"장착 불가 종류: {it['종류']} (무기/방어구/장신구만 가능)"))

    _remove(player, args.item, 1)  # 인벤토리에서 1개 소모
    gear = player.setdefault("장비", {"무기": None, "방어구": None, "장신구": None})
    prev = gear.get(slot)
    if isinstance(prev, dict):  # 기존 장비는 인벤토리로 되돌림
        _add(player, items, prev["id"], 1)
    gear[slot] = _equip_payload(args.item, it)
    C.write_player(path, player)
    C._emit({"ok": True, "command": "equip", "saved": path, "슬롯": slot,
             "착용": it["이름"], "해제": prev["이름"] if isinstance(prev, dict) else None,
             "장비": _gear_brief(gear)})


def cmd_unequip(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    gear = player.setdefault("장비", {"무기": None, "방어구": None, "장신구": None})
    item = gear.get(args.slot)
    if not isinstance(item, dict):
        raise SystemExit(C._err(f"{args.slot} 슬롯이 비어 있습니다."))
    _add(player, items, item["id"], 1)
    gear[args.slot] = None
    C.write_player(path, player)
    C._emit({"ok": True, "command": "unequip", "saved": path,
             "해제": item["이름"], "슬롯": args.slot, "장비": _gear_brief(gear)})


def cmd_use(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    it = get_item(items, args.item)
    if it["종류"] != "소모품":
        raise SystemExit(C._err(f"사용할 수 없는 종류: {it['종류']} (소모품만 use 가능)"))
    _remove(player, args.item, 1)

    eff = it.get("효과", {})
    applied = {}
    if "회복HP" in eff:
        before = player.get("HP", 0)
        player["HP"] = min(player.get("최대HP", before), before + eff["회복HP"])
        applied["회복HP"] = player["HP"] - before
    if "회복신수" in eff:
        before = player.get("신수", 0)
        player["신수"] = min(player.get("최대신수", before), before + eff["회복신수"])
        applied["회복신수"] = player["신수"] - before
    if "해제상태이상" in eff:
        target = eff["해제상태이상"]
        st = player.get("상태이상", [])
        if target == "전체":
            applied["해제"] = [s.get("kind") for s in st]
            player["상태이상"] = []
        else:
            keep = [s for s in st if s.get("kind") not in target]
            applied["해제"] = [s.get("kind") for s in st if s.get("kind") in target]
            player["상태이상"] = keep
    if "기능" in eff:
        applied["기능"] = eff["기능"]

    C.write_player(path, player)
    C._emit({"ok": True, "command": "use", "saved": path,
             "사용": it["이름"], "효과": applied,
             "HP": f"{player.get('HP')}/{player.get('최대HP')}",
             "신수": f"{player.get('신수')}/{player.get('최대신수')}"})


def cmd_buy(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    it = get_item(items, args.item)
    if it.get("가격", 0) <= 0:
        raise SystemExit(C._err(f"비매품입니다: {it['이름']}"))
    unit = round(it["가격"] * price_mult(player))
    total = unit * args.qty
    if player.get("돈", 0) < total:
        raise SystemExit(C._err(f"돈 부족: 보유 {player.get('돈',0)}, 필요 {total}"))
    player["돈"] -= total
    _add(player, items, args.item, args.qty)
    C.write_player(path, player)
    C._emit({"ok": True, "command": "buy", "saved": path,
             "구매": {"이름": it["이름"], "수량": args.qty, "단가": unit, "총액": total,
                    "평판배수": round(price_mult(player), 3)},
             "잔액": player["돈"]})


def cmd_sell(args):
    path = args.actor or C.DEFAULT_SAVE
    player = C.read_player(path)
    items = load_items()
    it = get_item(items, args.item)
    _remove(player, args.item, args.qty)
    unit = round(it.get("가격", 0) * SELL_RATE * price_mult(player))
    total = unit * args.qty
    player["돈"] = player.get("돈", 0) + total
    C.write_player(path, player)
    C._emit({"ok": True, "command": "sell", "saved": path,
             "판매": {"이름": it["이름"], "수량": args.qty, "단가": unit, "총액": total},
             "잔액": player["돈"]})


def _equip_payload(item_id, it):
    """장비 슬롯에 저장할 자족적(self-contained) 아이템 객체."""
    return {
        "id": item_id, "이름": it["이름"], "종류": it["종류"], "등급": it.get("등급"),
        "스탯보정": it.get("스탯보정", {}), "효과": it.get("효과", {}),
    }


def _gear_brief(gear):
    return {slot: (g["이름"] if isinstance(g, dict) else None)
            for slot, g in gear.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description="인벤토리·장비·경제 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p, item=True):
        p.add_argument("--actor")
        if item:
            p.add_argument("--item", required=True)

    a = sub.add_parser("add"); add_common(a)
    a.add_argument("--qty", type=int, default=1); a.set_defaults(func=cmd_add)
    rm = sub.add_parser("remove"); add_common(rm)
    rm.add_argument("--qty", type=int, default=1); rm.set_defaults(func=cmd_remove)
    eq = sub.add_parser("equip"); add_common(eq); eq.set_defaults(func=cmd_equip)
    ue = sub.add_parser("unequip"); add_common(ue, item=False)
    ue.add_argument("--slot", required=True, choices=["무기", "방어구", "장신구"])
    ue.set_defaults(func=cmd_unequip)
    us = sub.add_parser("use"); add_common(us); us.set_defaults(func=cmd_use)
    by = sub.add_parser("buy"); add_common(by)
    by.add_argument("--qty", type=int, default=1); by.set_defaults(func=cmd_buy)
    sl = sub.add_parser("sell"); add_common(sl)
    sl.add_argument("--qty", type=int, default=1); sl.set_defaults(func=cmd_sell)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
