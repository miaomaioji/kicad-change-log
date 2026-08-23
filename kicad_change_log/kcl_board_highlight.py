# -*- coding: utf-8 -*-
"""板上高亮与定位(依赖 pcbnew,仅在 KiCad 内运行)。"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import kcl_diff_engine as diff_engine


def _pcbnew():
    try:
        import pcbnew
        return pcbnew
    except Exception:
        return None


def _frame():
    pcbnew = _pcbnew()
    if pcbnew is None:
        return None
    try:
        import wx
    except ImportError:
        return None
    for win in wx.GetTopLevelWindows():
        name = type(win).__name__.upper()
        if "PCB_EDIT_FRAME" in name:
            return win
    try:
        frame = wx.FindWindowByName("PcbFrame")
        if frame is not None:
            return frame
    except Exception:
        pass
    return None


def _uuid_of(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:
        return ""


def _pos_of(item):
    try:
        p = item.GetPosition()
        return (p.x, p.y)
    except Exception:
        return (0, 0)


def _find_item(uuid):
    pcbnew = _pcbnew()
    if pcbnew is None or not uuid:
        return None
    board = pcbnew.GetBoard()
    if board is None:
        return None
    try:
        for fp in board.GetFootprints():
            if _uuid_of(fp) == uuid:
                return fp
        for tr in board.GetTracks():
            if _uuid_of(tr) == uuid:
                return tr
        for dr in board.GetDrawings():
            if _uuid_of(dr) == uuid:
                return dr
    except Exception:
        pass
    return None


def clear_highlight():
    pcbnew = _pcbnew()
    if pcbnew is None:
        return
    board = pcbnew.GetBoard()
    if board is None:
        return
    try:
        for fp in board.GetFootprints():
            fp.SetSelected(False)
        for tr in board.GetTracks():
            tr.SetSelected(False)
    except Exception:
        pass
    pcbnew.Refresh()


def highlight_change(change):
    """按 uuid 高亮板上元素并定位;未命中时按坐标定位。返回是否命中元素。"""
    found, _msg = highlight_change_info(change)
    return found


def highlight_change_info(change):
    """高亮并定位变更元素,返回 (是否命中元素, 提示文本)。

    被删除的元素已不存在于当前板,回退为定位到其原位置,
    提示文本说明原因,便于用户理解。
    """
    pcbnew = _pcbnew()
    if pcbnew is None:
        return False, "pcbnew 不可用"
    for uuid in (change.new_uuid, change.old_uuid):
        item = _find_item(uuid)
        if item is not None:
            try:
                item.SetSelected(True)
            except Exception:
                pass
            pcbnew.Refresh()
            _focus_item(item)
            return True, "已高亮并定位该元素"
    _focus_pos(getattr(change, "pos", (0, 0)))
    if change.change_type == diff_engine.REMOVED:
        return False, ("该元素在 B 版已被删除,当前板子上不存在,无法高亮;\n"
                       "已定位到其原位置。")
    return False, "当前板子中未找到该元素,已定位到其记录位置。"


def _focus_item(item):
    frame = _frame()
    if frame is None:
        return
    try:
        if hasattr(frame, "FocusOnItem"):
            frame.FocusOnItem(item)
            return
    except Exception:
        pass
    _focus_pos(_pos_of(item))


def _focus_pos(pos):
    pcbnew = _pcbnew()
    if pcbnew is None:
        return
    try:
        vec = pcbnew.VECTOR2I(int(pos[0]), int(pos[1]))
    except Exception:
        return
    frame = _frame()
    if frame is not None:
        try:
            if hasattr(frame, "FocusOnLocation"):
                frame.FocusOnLocation(vec)
                return
        except Exception:
            pass
        try:
            frame.GetScreen().SetCrossHairPosition(vec)
        except Exception:
            pass
    pcbnew.Refresh()
