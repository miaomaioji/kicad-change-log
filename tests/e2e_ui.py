# -*- coding: utf-8 -*-
"""端到端 UI 验证:用 KiCad 自带 Python 构建两个窗口并跑通数据流。

用法(必须用 KiCad 10 自带 Python):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests\\e2e_ui.py
"""

import os
import shutil
import sys
import tempfile

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_BASE, "..", "kicad_change_log")
sys.path.insert(0, os.path.abspath(_PKG))

import wx

import board_model
import config as config_mod
import log_window
import snapshot as snapshot_mod
import visual_window


def make_model_loader():
    cache = {}

    def load(path):
        path = os.path.abspath(path)
        if path not in cache:
            cache[path] = board_model.load_board(path)
        return cache[path]

    return load


def main():
    app = wx.App()
    tmp = tempfile.mkdtemp(prefix="kcl_ui_")
    try:
        board_path = os.path.join(tmp, "e2e.kicad_pcb")
        with open(os.path.join(_BASE, "e2e_a.kicad_pcb"), "r",
                  encoding="utf-8") as fh:
            content_a = fh.read()
        with open(os.path.join(_BASE, "e2e_b.kicad_pcb"), "r",
                  encoding="utf-8") as fh:
            content_b = fh.read()
        with open(board_path, "w", encoding="utf-8") as fh:
            fh.write(content_a)

        cfg = config_mod.Config(os.path.join(tmp, "settings.json"))
        store = snapshot_mod.SnapshotStore(board_path, cfg)
        entry1 = store.create_snapshot("基线")
        assert entry1 is not None
        with open(board_path, "w", encoding="utf-8") as fh:
            fh.write(content_b)
        entry2 = store.create_snapshot("修改后")
        assert entry2 is not None

        loader = make_model_loader()

        # ---- 窗口一:变动日志 ----
        log_win = log_window.LogWindow(None, store, cfg, loader)
        log_win.refresh()
        rows = log_win.listctrl.GetItemCount()
        print("日志窗口列表行数:", rows)
        assert rows == 6, "期望 6 条变更,实际 %d" % rows
        stats_text = log_win.lbl_stats.GetLabel()
        print("统计:", stats_text)
        assert "封装" in stats_text and "替换" in stats_text
        # 详情联动
        log_win.listctrl.Select(0)
        detail = log_win.txt_detail.GetValue()
        assert detail, "详情面板为空"
        print("详情示例:\n" + detail[:160])

        # ---- 窗口二:变更可视化 ----
        vis_win = visual_window.VisualWindow(None, store, cfg, loader)
        # 构造完成后自动对比并触发一次图层渲染
        layers = vis_win.layers
        print("有变更的图层:", layers)
        assert "F.Cu" in layers and "F.SilkS" in layers
        print("树节点统计:", vis_win.lbl_stats.GetLabel())
        assert vis_win.union_box[2] > vis_win.union_box[0]

        # ---- 板上高亮模块(独立进程无板子,仅验证函数可调用且不崩溃) ----
        import board_highlight
        board_highlight.clear_highlight()
        ch = vis_win.changes[0]
        hit = board_highlight.highlight_change(ch)
        print("高亮调用返回:", hit, "(独立进程无板子,False 为预期)")

        vis_win.Destroy()
        log_win.Destroy()
        print("全部通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
