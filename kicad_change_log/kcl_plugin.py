# -*- coding: utf-8 -*-
"""插件入口:初始化快照监听与两个窗口。"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import kcl_board_model as board_model
import kcl_config as config_mod
import kcl_log_window as log_window
import kcl_snapshot as snapshot_mod
import kcl_visual_window as visual_window

_state = {
    "config": None,
    "store": None,
    "watcher": None,
    "log_win": None,
    "visual_win": None,
    "board_path": "",
    "model_loader": None,
}


def current_board_path():
    """获取 pcbnew 中当前打开板文件的路径。"""
    try:
        import pcbnew
        board = pcbnew.GetBoard()
        if board is None:
            return ""
        return board.GetFileName() or ""
    except Exception:
        return ""


def make_model_loader():
    cache = {}

    def load(path):
        path = os.path.abspath(path)
        if path not in cache:
            cache[path] = board_model.load_board(path)
        return cache[path]

    return load


def _on_snapshot(entry):
    """自动快照产生后,刷新已打开的窗口。"""
    try:
        import wx
    except ImportError:
        return

    def update():
        log_win = _state.get("log_win")
        if log_win is not None:
            try:
                log_win.refresh()
            except Exception:
                pass
        visual_win = _state.get("visual_win")
        if visual_win is not None:
            try:
                visual_win.refresh_versions()
            except Exception:
                pass

    wx.CallAfter(update)


def open_log_window():
    import wx
    win = _state.get("log_win")
    if win is not None:
        try:
            win.Raise()
            win.refresh()
            return
        except Exception:
            _state["log_win"] = None
    cfg = _state.get("config")
    store = _state.get("store")
    if cfg is None or store is None:
        return
    win = log_window.LogWindow(
        None, store, cfg, _state.get("model_loader"),
        on_open_visual=open_visual_window,
        on_close=lambda: _state.__setitem__("log_win", None))
    _state["log_win"] = win
    win.Show()
    win.refresh()


def open_visual_window(sel_a=None, sel_b=None):
    import wx
    win = _state.get("visual_win")
    if win is not None:
        try:
            win.Raise()
            return
        except Exception:
            _state["visual_win"] = None
    cfg = _state.get("config")
    store = _state.get("store")
    if cfg is None or store is None:
        return
    win = visual_window.VisualWindow(
        None, store, cfg, _state.get("model_loader"),
        on_close=lambda: _state.__setitem__("visual_win", None),
        initial_a=sel_a, initial_b=sel_b)
    _state["visual_win"] = win
    win.Show()


def run():
    """插件主入口:在 KiCad 中由 ActionPlugin.Run() 调用。"""
    try:
        import wx
    except ImportError:
        return
    path = current_board_path()
    if not path or not os.path.isfile(path):
        dlg = wx.MessageDialog(None, "请先打开并保存一个 PCB 文件,再使用本插件。",
                               "项目操作日志与变更可视化",
                               wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()
        return

    cfg = config_mod.Config()
    _state["config"] = cfg
    _state["board_path"] = path
    _state["model_loader"] = make_model_loader()
    _state["store"] = snapshot_mod.SnapshotStore(path, cfg)

    watcher = _state.get("watcher")
    if watcher is not None and _state.get("board_path") != path:
        try:
            watcher.stop()
        except Exception:
            pass
        watcher = None
    if watcher is None:
        _state["watcher"] = snapshot_mod.BoardWatcher(_state["store"],
                                                      _on_snapshot)

    open_log_window()
    # 可视化窗口默认不弹出,由变动日志窗口「打开可视化窗口」按钮呼出
