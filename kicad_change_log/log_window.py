# -*- coding: utf-8 -*-
"""窗口一:变动日志窗口 —— 版本时间线 + 统计 + 逐条明细 + 详情面板。

支持「实时对比」开关:开启后每 2 秒将当前内存板临时导出,
与最近一次快照实时对比,编辑操作即时可见。
"""

import os
import sys
import tempfile

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import wx

import board_model
import config as config_mod
import diff_engine
import snapshot as snapshot_mod
import units

try:
    import board_highlight
except Exception:  # noqa: BLE001
    board_highlight = None

_COL_DEFS = [("位号", 150), ("变更描述", 640), ("图层", 150)]

# 深色主题友好配色:高对比背景 + 白/黑字
_COLOURS = {
    diff_engine.ADDED: wx.Colour(27, 94, 32),
    diff_engine.REMOVED: wx.Colour(183, 28, 28),
    diff_engine.REPLACED: wx.Colour(81, 45, 168),
    diff_engine.MODIFIED: wx.Colour(255, 193, 7),
}

_TEXT_COLOURS = {
    diff_engine.ADDED: wx.Colour(255, 255, 255),
    diff_engine.REMOVED: wx.Colour(225, 215, 215),
    diff_engine.REPLACED: wx.Colour(255, 255, 255),
    diff_engine.MODIFIED: wx.Colour(0, 0, 0),
}

_LIVE_INTERVAL_MS = 2000

_KIND_ORDER = [board_model.KIND_FOOTPRINT, board_model.KIND_SEGMENT,
               board_model.KIND_VIA, board_model.KIND_ZONE,
               board_model.KIND_TEXT, board_model.KIND_LINE,
               board_model.KIND_ARC, board_model.KIND_CIRCLE,
               board_model.KIND_RECT, board_model.KIND_CURVE,
               board_model.KIND_DIM]


class LogWindow(wx.Frame):
    def __init__(self, parent, store, config, model_loader,
                 on_open_visual=None, on_close=None):
        super().__init__(parent, title="变动日志 - 项目操作日志与变更可视化 v%s"
                         % config_mod.VERSION,
                         size=(1200, 760),
                         style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER)
        self.store = store
        self.config = config
        self.model_loader = model_loader
        self.on_open_visual = on_open_visual
        self.on_close = on_close
        self.changes = []
        self.unit = "mm"
        self._updating = False
        self.live_mode = False
        self.live_hash = None
        self._computing = False
        self.live_dir = tempfile.mkdtemp(prefix="kcl_live_")
        self.live_path = os.path.join(self.live_dir, "live.kicad_pcb")

        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        # ---- 版本选择 ----
        ver_row = wx.BoxSizer(wx.HORIZONTAL)
        ver_row.Add(wx.StaticText(panel, label="对比版本 A(旧):"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        self.choice_a = wx.Choice(panel)
        ver_row.Add(self.choice_a, 1, wx.LEFT, 4)
        ver_row.Add(wx.StaticText(panel, label="B(新):"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self.choice_b = wx.Choice(panel)
        ver_row.Add(self.choice_b, 1, wx.LEFT, 4)
        self.btn_refresh = wx.Button(panel, label="刷新")
        ver_row.Add(self.btn_refresh, 0, wx.LEFT, 8)
        self.check_live = wx.CheckBox(panel, label="实时对比")
        self.check_live.SetToolTip("每 2 秒将当前板与最近快照实时对比,编辑操作即时可见")
        ver_row.Add(self.check_live, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        root.Add(ver_row, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)

        # ---- 统计 ----
        self.lbl_stats = wx.StaticText(panel, label="统计: -")
        root.Add(self.lbl_stats, 0, wx.EXPAND | wx.LEFT, 6)

        # ---- 过滤 ----
        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_row.Add(wx.StaticText(panel, label="类型过滤:"),
                       0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        filter_choices = ["全部"] + [board_model.KINDS_CN[k] for k in _KIND_ORDER]
        self.choice_filter = wx.Choice(panel, choices=filter_choices)
        self.choice_filter.SetSelection(0)
        filter_row.Add(self.choice_filter, 0, wx.LEFT, 4)
        root.Add(filter_row, 0, wx.EXPAND | wx.BOTTOM, 4)

        # ---- 列表/详情分隔条(详情高度可拖动调整) ----
        split = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        top_panel = wx.Panel(split)
        bottom_panel = wx.Panel(split)
        split.SplitHorizontally(top_panel, bottom_panel, 480)
        split.SetMinimumPaneSize(120)
        split.SetSashGravity(0.85)

        top_sizer = wx.BoxSizer(wx.VERTICAL)
        self.listctrl = wx.ListCtrl(top_panel,
                                    style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (title, width) in enumerate(_COL_DEFS):
            self.listctrl.InsertColumn(idx, title, width=width)
        font = self.listctrl.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        self.listctrl.SetFont(font)
        top_sizer.Add(self.listctrl, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)

        bottom_sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_detail = wx.StaticText(bottom_panel,
                                   label="详细信息(拖动上方分隔条调整高度)")
        bottom_sizer.Add(lbl_detail, 0, wx.LEFT | wx.TOP, 4)
        self.lbl_detail_summary = wx.StaticText(bottom_panel, label="")
        summary_font = self.lbl_detail_summary.GetFont()
        self.lbl_detail_summary.SetFont(
            wx.Font(summary_font.GetPointSize() + 1, wx.FONTFAMILY_DEFAULT,
                    wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        bottom_sizer.Add(self.lbl_detail_summary, 0, wx.EXPAND | wx.LEFT, 4)
        self.detail_list = wx.ListCtrl(bottom_panel,
                                       style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for i, (title, width) in enumerate((("属性", 110), ("变更前", 320),
                                            ("变更后", 320))):
            self.detail_list.InsertColumn(i, title, width=width)
        bottom_sizer.Add(self.detail_list, 1, wx.EXPAND | wx.ALL, 4)
        self.txt_detail = wx.TextCtrl(bottom_panel,
                                      style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_detail.SetMinSize((-1, 70))
        bottom_sizer.Add(self.txt_detail, 0, wx.EXPAND | wx.ALL, 4)
        bottom_panel.SetSizer(bottom_sizer)

        root.Add(split, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

        # ---- 按钮 ----
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_snapshot = wx.Button(panel, label="记录快照")
        self.btn_highlight = wx.Button(panel, label="在板上高亮")
        self.btn_visual = wx.Button(panel, label="打开可视化窗口")
        self.btn_close = wx.Button(panel, label="关闭")
        btn_row.Add(self.btn_snapshot, 0, wx.LEFT, 6)
        btn_row.Add(self.btn_highlight, 0, wx.LEFT, 6)
        btn_row.Add(self.btn_visual, 0, wx.LEFT, 6)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(self.btn_close, 0, wx.RIGHT | wx.LEFT, 6)
        root.Add(btn_row, 0, wx.EXPAND | wx.BOTTOM, 8)

        panel.SetSizer(root)

        # ---- 事件 ----
        self.choice_a.Bind(wx.EVT_CHOICE, lambda e: self._on_compare())
        self.choice_b.Bind(wx.EVT_CHOICE, lambda e: self._on_compare())
        self.choice_filter.Bind(wx.EVT_CHOICE, lambda e: self._fill_list())
        self.check_live.Bind(wx.EVT_CHECKBOX, self._on_live_toggle)
        self.btn_refresh.Bind(wx.EVT_BUTTON, lambda e: self.refresh())
        self.btn_snapshot.Bind(wx.EVT_BUTTON, lambda e: self._on_snapshot())
        self.btn_highlight.Bind(wx.EVT_BUTTON, lambda e: self._on_highlight())
        self.btn_visual.Bind(wx.EVT_BUTTON, lambda e: self._open_visual())
        self.btn_close.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        self.listctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.live_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self._on_live_tick(), self.live_timer)

    # ------------------------------------------------------------ 数据
    def _versions(self):
        current = {"file": self.store.board_path, "time": os.path.getmtime(
            self.store.board_path) if os.path.isfile(self.store.board_path) else 0,
            "note": "(未快照)", "current": True}
        return [current] + self.store.entries()

    def _selected_paths(self):
        versions = self._versions()
        a = self.choice_a.GetSelection()
        b = self.choice_b.GetSelection()
        if a < 0 or b < 0 or a >= len(versions) or b >= len(versions):
            return None
        return (self.store.path_for(versions[a]),
                self.store.path_for(versions[b]))

    def _reload_versions(self, keep=None):
        self._updating = True
        try:
            versions = self._versions()
            labels = [snapshot_mod.version_label(v) for v in versions]
            sel_a = self.choice_a.GetSelection()
            sel_b = self.choice_b.GetSelection()
            self.choice_a.SetItems(labels)
            self.choice_b.SetItems(labels)
            n = len(labels)
            if n >= 2:
                if not (0 <= sel_a < n):
                    sel_a = n - 2
                if not (0 <= sel_b < n):
                    sel_b = n - 1
                self.choice_a.SetSelection(sel_a)
                self.choice_b.SetSelection(sel_b)
            else:
                self.choice_a.SetSelection(0)
                self.choice_b.SetSelection(0)
        finally:
            self._updating = False

    def _compute(self):
        paths = self._selected_paths()
        if paths is None:
            self.changes = []
            return False
        if not all(os.path.isfile(p) for p in paths):
            self.changes = []
            return False
        if self.config.get("units_follow_board"):
            self.unit = units.board_unit()
        try:
            old = self.model_loader(paths[0])
            new = self.model_loader(paths[1])
            self.changes = diff_engine.diff(old, new)
        except Exception as exc:  # noqa: BLE001
            self.changes = []
            self.lbl_stats.SetLabel("对比失败: %s" % exc)
            return False
        return True

    # ------------------------------------------------------------ UI
    def refresh(self):
        try:
            self._reload_versions()
        except Exception:
            pass
        if self.live_mode:
            self._refresh_live(force=True)
        else:
            self._on_compare()

    def _on_compare(self):
        if self._updating or self.live_mode:
            return
        if not self._compute():
            self._fill_list()
            return
        st = diff_engine.stats(self.changes)
        parts = []
        for kind in _KIND_ORDER:
            d = st.get(kind)
            if not d:
                continue
            parts.append("%s 新增 %d / 删除 %d / 替换 %d / 修改 %d"
                         % (board_model.KINDS_CN[kind], d["added"],
                            d["removed"], d["replaced"], d["modified"]))
        self.lbl_stats.SetLabel(
            "统计: " + (" | ".join(parts) if parts else "无变更"))
        self._fill_list()

    # ------------------------------------------------------------ 实时对比
    def _on_live_toggle(self, event):
        enabled = self.check_live.IsChecked()
        if enabled:
            if not self.store.entries():
                wx.MessageBox("实时对比需要至少一个快照作为基准,"
                              "请先点「记录快照」。", "实时对比",
                              wx.OK | wx.ICON_INFORMATION)
                self.check_live.SetValue(False)
                return
            self.live_mode = True
            self.live_hash = None
            self.choice_a.Disable()
            self.choice_b.Disable()
            self.live_timer.Start(_LIVE_INTERVAL_MS)
            self._refresh_live(force=True)
        else:
            self.live_mode = False
            self.live_timer.Stop()
            self.choice_a.Enable()
            self.choice_b.Enable()
            self._on_compare()

    def _on_live_tick(self):
        self._refresh_live(force=False)

    def _refresh_live(self, force=False):
        if self._computing:
            return
        try:
            import pcbnew
        except ImportError:
            return
        board = pcbnew.GetBoard()
        if board is None:
            return
        if not force and not board.IsModified() and self.live_hash is not None:
            return
        entries = self.store.entries()
        if not entries:
            return
        self._computing = True
        try:
            pcbnew.SaveBoard(self.live_path, board)
            digest = snapshot_mod.file_hash(self.live_path)
            if not force and digest == self.live_hash:
                return
            self.live_hash = digest
            if self.config.get("units_follow_board"):
                self.unit = units.board_unit()
            old = board_model.load_board(self.store.path_for(entries[-1]))
            new = board_model.load_board(self.live_path)
            self.changes = diff_engine.diff(old, new)
            st = diff_engine.stats(self.changes)
            parts = []
            for kind in _KIND_ORDER:
                d = st.get(kind)
                if not d:
                    continue
                parts.append("%s 新增 %d / 删除 %d / 替换 %d / 修改 %d"
                             % (board_model.KINDS_CN[kind], d["added"],
                                d["removed"], d["replaced"], d["modified"]))
            base = snapshot_mod.version_label(entries[-1])
            self.lbl_stats.SetLabel(
                "实时·基准 %s | " % base
                + (" | ".join(parts) if parts else "无变更"))
            self._fill_list()
        except Exception as exc:  # noqa: BLE001
            self.lbl_stats.SetLabel("实时对比失败: %s" % exc)
        finally:
            self._computing = False

    def _filtered(self):
        sel = self.choice_filter.GetSelection()
        if sel <= 0:
            changes = list(self.changes)
        else:
            kind = _KIND_ORDER[sel - 1]
            changes = [c for c in self.changes if c.kind == kind]
        order = {diff_engine.REMOVED: 0, diff_engine.ADDED: 1,
                 diff_engine.REPLACED: 2, diff_engine.MODIFIED: 3}
        return sorted(changes,
                      key=lambda c: (order.get(c.change_type, 9),
                                     (c.ref or c.name).lower()))

    def _ensure_columns(self):
        count = self.listctrl.GetColumnCount()
        for i in range(count, len(_COL_DEFS)):
            title, width = _COL_DEFS[i]
            self.listctrl.InsertColumn(i, title, width=width)

    def _fill_list(self):
        self.listctrl.DeleteAllItems()
        self.txt_detail.SetValue("")
        self._ensure_columns()
        filtered = self._filtered()
        for idx, ch in enumerate(filtered):
            type_cn = diff_engine.CHANGE_CN.get(ch.change_type, ch.change_type)
            if ch.change_type == diff_engine.ADDED:
                label = "+ " + diff_engine.change_label(ch)
                desc = "%s %s" % (type_cn,
                                   units.format_desc_line(ch, self.unit,
                                                          decimals=2))
            elif ch.change_type == diff_engine.REMOVED:
                label = "- " + diff_engine.change_label(ch)
                desc = "%s %s" % (type_cn,
                                   units.format_desc_line(ch, self.unit,
                                                          decimals=2))
            elif ch.change_type == diff_engine.REPLACED:
                label = "↔ " + diff_engine.change_label(ch)
                desc = units.format_first_attr(ch, self.unit, decimals=2)
            elif ch.attrs:
                label = "~ " + diff_engine.change_label(ch)
                desc = units.format_first_attr(ch, self.unit, decimals=2)
            else:
                label = diff_engine.change_label(ch)
                desc = type_cn
            if not label.strip("+ -~↔ "):
                label = (ch.new_uuid or ch.old_uuid or "")[:8] or "(无位号)"
            if not desc:
                desc = type_cn
            layer = board_model.layer_display(ch.layer) if ch.layer else "—"
            row = self.listctrl.InsertItem(idx, label)
            self.listctrl.SetItem(row, 1, units.shorten(desc, 40))
            self.listctrl.SetItem(row, 2, layer)
            colour = _COLOURS.get(ch.change_type)
            if colour is not None:
                self.listctrl.SetItemBackgroundColour(row, colour)
                self.listctrl.SetItemTextColour(
                    row, _TEXT_COLOURS.get(ch.change_type, wx.Colour(0, 0, 0)))
            self.listctrl.SetItemData(row, idx)

    def _on_item_selected(self, event):
        row = event.GetIndex()
        filtered = self._filtered()
        if not (0 <= row < len(filtered)):
            return
        self._show_detail(filtered[row])

    def _show_detail(self, ch):
        """详情面板:标题 + 属性级前后双列对比 + uuid/摘要。"""
        type_cn = diff_engine.CHANGE_CN.get(ch.change_type, ch.change_type)
        label = diff_engine.change_label(ch)
        self.lbl_detail_summary.SetLabel("%s [%s]" % (label, type_cn))
        self.detail_list.DeleteAllItems()
        row_idx = 0
        for ac in ch.attrs:
            item = self.detail_list.InsertItem(row_idx, ac.attr)
            self.detail_list.SetItem(
                item, 1, units.fmt_value(ac.old, ac.value_type, self.unit))
            self.detail_list.SetItem(
                item, 2, units.fmt_value(ac.new, ac.value_type, self.unit))
            row_idx += 1
        for key, value, vtype in ch.desc:
            item = self.detail_list.InsertItem(row_idx, key)
            if ch.change_type == diff_engine.ADDED:
                self.detail_list.SetItem(item, 1, "—")
                self.detail_list.SetItem(
                    item, 2, units.fmt_value(value, vtype, self.unit))
            else:
                self.detail_list.SetItem(
                    item, 1, units.fmt_value(value, vtype, self.unit))
                self.detail_list.SetItem(item, 2, "—")
            row_idx += 1
        lines = ["变更摘要: %s" % units.format_change_line(ch, self.unit)]
        if ch.old_uuid:
            lines.append("旧 uuid: %s" % ch.old_uuid)
        if ch.new_uuid:
            lines.append("新 uuid: %s" % ch.new_uuid)
        self.txt_detail.SetValue("\n".join(lines))

    # ------------------------------------------------------------ 动作
    def _on_snapshot(self):
        entry = self.store.create_snapshot("手动快照")
        if entry is None:
            wx.MessageBox("板文件与上一条快照内容相同,无需新快照。",
                          "记录快照", wx.OK | wx.ICON_INFORMATION)
            return
        self.refresh()

    def _on_highlight(self):
        row = self.listctrl.GetFirstSelected()
        filtered = self._filtered()
        if row < 0 or row >= len(filtered):
            return
        ch = filtered[row]
        if board_highlight is None:
            return
        found, message = board_highlight.highlight_change_info(ch)
        title = "在板上高亮"
        if found:
            wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION)

    def _open_visual(self):
        if self.on_open_visual is not None:
            self.on_open_visual(self.choice_a.GetSelection(),
                                self.choice_b.GetSelection())

    def _on_close(self, event):
        self.live_timer.Stop()
        try:
            import shutil
            shutil.rmtree(self.live_dir, ignore_errors=True)
        except Exception:
            pass
        if self.on_close is not None:
            self.on_close()
        event.Skip()
