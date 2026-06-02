#!/usr/bin/env python3
"""세이브 백업·복원 도구 (save.py)

  save      player.json + world_state.json 을 타임스탬프 스냅샷으로 백업
  load      가장 최근(또는 지정) 스냅샷을 복원
  autosave  층 이동·전투 종료·퀘스트 완료 등에서 자동 백업(오래된 자동백업은 정리)
  list      스냅샷 목록

스냅샷은 save/backups/<스냅id>/ 폴더에 player.json·world_state.json·manifest.json 로 저장된다.
"""

import argparse
import datetime
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve as R  # noqa: E402

SAVE_DIR = os.path.join(R.BASE_DIR, "save")
DEFAULT_PLAYER = os.path.join(SAVE_DIR, "player.json")
DEFAULT_WORLD = os.path.join(SAVE_DIR, "world_state.json")
DEFAULT_BACKUPS = os.path.join(SAVE_DIR, "backups")
KEEP_AUTOSAVES = 10


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _snap_id(label, backups):
    base = f"save_{_ts()}" + (f"_{label}" if label else "")
    snap = base
    i = 1
    while os.path.exists(os.path.join(backups, snap)):
        snap = f"{base}_{i}"
        i += 1
    return snap


def _copy_if_exists(src, dst):
    if os.path.exists(src):
        shutil.copy2(src, dst)
        return True
    return False


def do_save(player, world, backups, label=None, reason="manual"):
    os.makedirs(backups, exist_ok=True)
    snap = _snap_id(label, backups)
    snap_dir = os.path.join(backups, snap)
    os.makedirs(snap_dir)
    saved = {}
    saved["player"] = _copy_if_exists(player, os.path.join(snap_dir, "player.json"))
    saved["world"] = _copy_if_exists(world, os.path.join(snap_dir, "world_state.json"))
    manifest = {
        "스냅id": snap, "시각": datetime.datetime.now().isoformat(timespec="seconds"),
        "라벨": label, "사유": reason,
        "원본": {"player": player, "world": world},
        "포함": saved,
    }
    with open(os.path.join(snap_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return snap, manifest


def list_snapshots(backups):
    if not os.path.isdir(backups):
        return []
    snaps = []
    for name in sorted(os.listdir(backups)):
        mpath = os.path.join(backups, name, "manifest.json")
        if os.path.isfile(mpath):
            with open(mpath, "r", encoding="utf-8") as fh:
                snaps.append(json.load(fh))
    return snaps  # 이름(타임스탬프) 오름차순


# ──────────────────────────────────────────────────────────────────────────
# 명령
# ──────────────────────────────────────────────────────────────────────────

def cmd_save(args):
    snap, manifest = do_save(args.player, args.world, args.dir,
                             label=args.label, reason="manual")
    _emit({"ok": True, "command": "save", "스냅id": snap,
           "시각": manifest["시각"], "포함": manifest["포함"]})


def cmd_autosave(args):
    snap, manifest = do_save(args.player, args.world, args.dir,
                             label="auto", reason=args.reason or "auto")
    # 오래된 자동백업 정리
    autos = [s for s in list_snapshots(args.dir) if s.get("라벨") == "auto"]
    removed = []
    if len(autos) > KEEP_AUTOSAVES:
        for s in autos[:-KEEP_AUTOSAVES]:
            shutil.rmtree(os.path.join(args.dir, s["스냅id"]), ignore_errors=True)
            removed.append(s["스냅id"])
    _emit({"ok": True, "command": "autosave", "스냅id": snap,
           "사유": manifest["사유"], "정리된_오래된자동백업": removed,
           "보관개수": KEEP_AUTOSAVES})


def cmd_load(args):
    snaps = list_snapshots(args.dir)
    if not snaps:
        raise SystemExit(json.dumps(
            {"ok": False, "error": f"백업이 없습니다: {args.dir}"},
            ensure_ascii=False, indent=2))
    if args.id:
        target = next((s for s in snaps if s["스냅id"] == args.id), None)
        if target is None:
            raise SystemExit(json.dumps(
                {"ok": False, "error": f"스냅id 없음: {args.id}"},
                ensure_ascii=False, indent=2))
    else:
        target = snaps[-1]  # 최신

    snap_dir = os.path.join(args.dir, target["스냅id"])
    # 복원 전, 현재 상태를 안전망으로 백업
    pre = None
    if os.path.exists(args.player) or os.path.exists(args.world):
        pre, _ = do_save(args.player, args.world, args.dir,
                         label="prerestore", reason="load 직전 안전백업")
    restored = []
    if _copy_if_exists(os.path.join(snap_dir, "player.json"), args.player):
        restored.append("player.json")
    if _copy_if_exists(os.path.join(snap_dir, "world_state.json"), args.world):
        restored.append("world_state.json")
    _emit({"ok": True, "command": "load", "복원한_스냅id": target["스냅id"],
           "스냅시각": target["시각"], "복원파일": restored,
           "load직전_안전백업": pre})


def cmd_list(args):
    snaps = list_snapshots(args.dir)
    _emit({"ok": True, "command": "list", "개수": len(snaps),
           "스냅샷": [{"스냅id": s["스냅id"], "시각": s["시각"],
                    "라벨": s.get("라벨"), "사유": s.get("사유")} for s in snaps]})


def main(argv=None):
    parser = argparse.ArgumentParser(description="세이브 백업·복원 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--player", default=DEFAULT_PLAYER)
        p.add_argument("--world", default=DEFAULT_WORLD)
        p.add_argument("--dir", default=DEFAULT_BACKUPS)

    sv = sub.add_parser("save"); common(sv)
    sv.add_argument("--label"); sv.set_defaults(func=cmd_save)
    au = sub.add_parser("autosave"); common(au)
    au.add_argument("--reason"); au.set_defaults(func=cmd_autosave)
    ld = sub.add_parser("load"); common(ld)
    ld.add_argument("--id", help="복원할 스냅id(생략 시 최신)")
    ld.set_defaults(func=cmd_load)
    ls = sub.add_parser("list"); common(ls); ls.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
