# -*- coding: utf-8 -*-
"""快照数据层与校准标记注入的运行时测试(纯标准库部分)。

用法:
    python tests/test_snapshot.py
"""

import os
import shutil
import sys
import tempfile

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_BASE, "..", "kicad_change_log")
sys.path.insert(0, os.path.abspath(_PKG))

import kcl_board_model as board_model
import kcl_config as config_mod
import kcl_renderer as renderer
import kcl_snapshot as snapshot_mod


class FakeConfig:
    def __init__(self, **kwargs):
        self.values = {
            "snapshot_dir_name": "snapshots",
            "max_snapshots": 200,
            "poll_interval_s": 2.0,
            "auto_snapshot": True,
            "kicad_cli_path": "",
            "render_quality": "high",
        }
        self.values.update(kwargs)

    def get(self, key):
        return self.values.get(key)


def main():
    failures = []

    def check(name, cond, detail=""):
        if cond:
            print("PASS:", name)
        else:
            failures.append((name, detail))
            print("FAIL:", name, detail)

    tmp = tempfile.mkdtemp(prefix="kcl_test_")
    try:
        board_path = os.path.join(tmp, "test.kicad_pcb")
        with open(os.path.join(_BASE, "sample_a.kicad_pcb"), "r",
                  encoding="utf-8") as fh:
            content = fh.read()
        with open(board_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        cfg = FakeConfig()
        store = snapshot_mod.SnapshotStore(board_path, cfg)

        # 首次快照
        entry1 = store.create_snapshot("初始快照")
        check("首次快照生成", entry1 is not None and entry1["note"] == "初始快照")
        check("快照文件存在", entry1 is not None
              and os.path.isfile(store.path_for(entry1)))
        # 内容未变 → 去重
        entry_dup = store.create_snapshot("重复")
        check("相同内容去重", entry_dup is None)

        # 修改后再快照
        with open(board_path, "a", encoding="utf-8") as fh:
            fh.write("\n")
        entry2 = store.create_snapshot("手动快照")
        check("二次快照生成", entry2 is not None and entry2 != entry1)
        check("快照顺序", len(store.entries()) == 2,
              "实际 %d" % len(store.entries()))

        # 快照上限裁剪
        cfg.values["max_snapshots"] = 1
        store.prune()
        check("超出上限裁剪", len(store.entries()) == 1,
              "实际 %d" % len(store.entries()))
        remaining = store.entries()[0]
        check("保留最新", remaining["file"] == entry2["file"],
              str(remaining))

        # 版本标签
        label = snapshot_mod.version_label({"time": 0, "note": "测试",
                                            "current": False})
        check("版本标签", label.endswith("测试"), label)
        cur_label = snapshot_mod.version_label({"time": 0, "current": True})
        check("当前板子标签", cur_label.startswith("当前板子"), cur_label)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 校准标记注入(renderer 纯逻辑) ----
    tmp2 = tempfile.mkdtemp(prefix="kcl_calib_")
    try:
        src = os.path.join(_BASE, "sample_a.kicad_pcb")
        dst = os.path.join(tmp2, "calib.kicad_pcb")
        pts = renderer._inject_markers(src, dst, (0, 0, 100000000, 60000000))
        check("标记坐标", len(pts) == 2 and pts[0] != pts[1], repr(pts))
        model = board_model.load_board(dst)
        circles = [e for e in model.elements
                   if e.kind == board_model.KIND_CIRCLE]
        check("标记已注入", len(circles) == 2, "实际 %d" % len(circles))
        check("标记图层", all(c.layer == renderer.CALIB_LAYER for c in circles),
              str([c.layer for c in circles]))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    cli = renderer.find_kicad_cli("")
    print("INFO: 本机 kicad-cli:", cli or "(未找到,不影响纯逻辑测试)")

    print()
    if failures:
        print("共 %d 项失败" % len(failures))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
