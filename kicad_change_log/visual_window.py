# -*- coding: utf-8 -*-
"""窗口二:变更可视化窗口(参照 DRC + 嘉立创 DFM 风格)。

左侧:按图层分组的变动列表(点击联动定位);右侧:图层对比图。
三种对比模式:并排 / 红绿叠加 / 滑块分割。
"""

import os
import sys
import tempfile
import time

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import wx

import board_model
import config as config_mod
import diff_engine
import renderer
import snapshot as snapshot_mod
import units

try:
    import board_highlight
except Exception:  # noqa: BLE001
    board_highlight = None

MODE_SIDE = 0
MODE_OVERLAY = 1
MODE_SPLIT = 2

_MARKER_COLOUR = wx.Colour(255, 230, 0)


class CompareCanvas(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        self.result = None
        self.mode = MODE_SIDE
        self.split = 0.5
        self.markers = []
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self._drag = None
        self._cache = {}
        self.SetBackgroundColour(wx.Colour(24, 24, 24))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_LEFT_DCLICK, lambda e: self.reset_view())
        self.Bind(wx.EVT_MIDDLE_UP, lambda e: self.reset_view())
        self._last_fit = None
        self.on_cursor = None

    def set_result(self, result):
        self.result = result
        self._cache = {}
        self.reset_view()

    def set_mode(self, mode):
        self.mode = mode
        self.Refresh()

    def set_split(self, value):
        self.split = value / 100.0
        self.Refresh()

    def set_markers(self, markers):
        self.markers = markers or []
        self.Refresh()

    # ------------------------------------------------ 视图交互
    def reset_view(self):
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self._last_fit = None
        self.Refresh()

    def _area_at(self, x, width, height):
        if self.mode == MODE_SIDE:
            if x < width // 2:
                return (0, 0, width // 2, height)
            return (width // 2, 0, width - width // 2, height)
        return (0, 0, width, height)

    def _on_wheel(self, event):
        if self.result is None:
            return
        factor = 1.25 if event.GetWheelRotation() > 0 else 0.8
        new_zoom = max(0.2, min(20.0, self.zoom * factor))
        ratio = new_zoom / self.zoom if self.zoom else 1.0
        width, height = self.GetClientSize()
        cursor = event.GetPosition()
        area = self._area_at(cursor[0], width, height)
        if area is not None:
            ax, ay, aw, ah = area
            cx = ax + aw / 2.0 + self.pan[0]
            cy = ay + ah / 2.0 + self.pan[1]
            cx = cursor[0] - (cursor[0] - cx) * ratio
            cy = cursor[1] - (cursor[1] - cy) * ratio
            self.pan[0] = cx - (ax + aw / 2.0)
            self.pan[1] = cy - (ay + ah / 2.0)
        self.zoom = new_zoom
        self.Refresh()
        self._notify_cursor(cursor)

    def _on_left_down(self, event):
        if self.result is None:
            return
        self._drag = event.GetPosition()
        self.CaptureMouse()

    def _on_motion(self, event):
        pos = event.GetPosition()
        if self._drag is not None and self.HasCapture():
            self.pan[0] += pos[0] - self._drag[0]
            self.pan[1] += pos[1] - self._drag[1]
            self._drag = pos
            self.Refresh()
        self._notify_cursor(pos)

    def _screen_to_board(self, x, y):
        if self.result is None or self._last_fit is None:
            return None
        sx, sy, ox, oy = self._last_fit
        if sx <= 0 or sy <= 0:
            return None
        px = (x - ox) / sx
        py = (y - oy) / sy
        aff = self.result["aff"]
        if abs(aff[0]) < 1e-12 or abs(aff[2]) < 1e-12:
            return None
        return ((px - aff[1]) / aff[0], (py - aff[3]) / aff[2])

    def _notify_cursor(self, screen_pos):
        if self.on_cursor is None:
            return
        self.on_cursor(self._screen_to_board(screen_pos[0], screen_pos[1]),
                       self.zoom)

    def _on_left_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        self._drag = None

    def _bitmap(self, img, dw, dh):
        key = (id(img), dw, dh)
        bmp = self._cache.get(key)
        if bmp is None:
            bmp = wx.Bitmap(img.Scale(dw, dh, wx.IMAGE_QUALITY_HIGH))
            if len(self._cache) > 8:
                self._cache.clear()
            self._cache[key] = bmp
        return bmp

    def _draw_view(self, dc, img, x, y, w, h):
        iw, ih = img.GetWidth(), img.GetHeight()
        if iw <= 0 or ih <= 0:
            return None
        scale = min(w / float(iw), h / float(ih)) * self.zoom
        dw, dh = max(1, int(iw * scale)), max(1, int(ih * scale))
        cx = x + w / 2.0 + self.pan[0]
        cy = y + h / 2.0 + self.pan[1]
        ox = int(cx - dw / 2.0)
        oy = int(cy - dh / 2.0)
        dc.DrawBitmap(self._bitmap(img, dw, dh), ox, oy, False)
        # 返回与绘制完全一致的像素映射:图像像素 → 屏幕像素
        return (dw / float(iw), dh / float(ih), ox, oy)

    def _on_paint(self, event):
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(24, 24, 24)))
        dc.Clear()
        if self.result is None:
            dc.SetTextForeground(wx.Colour(200, 200, 200))
            dc.DrawText("正在渲染…(或从左侧选择一个变更图层)\n"
                        "滚轮缩放 · 左键拖拽平移 · 双击复位", 20, 20)
            return
        width, height = self.GetClientSize()
        if width < 50 or height < 50:
            return
        img_a = self.result["img_a"]
        img_aligned = self.result["aligned"]
        overlay = self.result["overlay"]
        fits = []
        if self.mode == MODE_SIDE:
            fit_a = self._draw_view(dc, img_a, 0, 0, width // 2, height)
            fit_b = self._draw_view(dc, img_aligned, width // 2, 0,
                                    width - width // 2, height)
            if fit_a is not None:
                fits.append(fit_a)
            if fit_b is not None:
                fits.append(fit_b)
        elif self.mode == MODE_OVERLAY:
            fit = self._draw_view(dc, overlay, 0, 0, width, height)
            if fit is not None:
                fits.append(fit)
        else:  # 滑块分割
            fit = self._draw_view(dc, img_a, 0, 0, width, height)
            if fit is not None:
                fits.append(fit)
            dc.SetClippingRegion(int(width * self.split), 0,
                                 width - int(width * self.split), height)
            self._draw_view(dc, img_aligned, 0, 0, width, height)
            dc.DestroyClippingRegion()
            dc.SetPen(wx.Pen(wx.Colour(255, 255, 255), 2))
            dc.DrawLine(int(width * self.split), 0,
                        int(width * self.split), height)
        self._last_fit = fits[0] if fits else None
        self._paint_markers(dc, fits)

    def _paint_markers(self, dc, fits):
        if not fits or not self.markers or self.result is None:
            return
        aff = self.result["aff"]
        for fit in fits:
            sx, sy, ox, oy = fit
            for pos, _label in self.markers:
                px = aff[0] * pos[0] + aff[1]
                py = aff[2] * pos[1] + aff[3]
                cx = int(ox + px * sx)
                cy = int(oy + py * sy)
                radius = 12
                # 白色描边 + 黄色标记(恒定屏幕尺寸)
                dc.SetPen(wx.Pen(wx.Colour(255, 255, 255), 4))
                dc.DrawCircle(cx, cy, radius)
                dc.SetPen(wx.Pen(_MARKER_COLOUR, 2))
                dc.DrawCircle(cx, cy, radius)
                dc.DrawLine(cx - radius - 6, cy, cx + radius + 6, cy)
                dc.DrawLine(cx, cy - radius - 6, cx, cy + radius + 6)


class VisualWindow(wx.Frame):
    def __init__(self, parent, store, config, model_loader,
                 on_close=None, initial_a=None, initial_b=None):
        super().__init__(parent, title="变更可视化 - 项目操作日志与变更可视化 v%s"
                         % config_mod.VERSION,
                         size=(1360, 860),
                         style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER)
        self.store = store
        self.config = config
        self.model_loader = model_loader
        self.on_close = on_close
        self.initial_a = initial_a
        self.initial_b = initial_b
        self.changes = []
        self.item_map = {}
        self.layers = []
        self.current_change = None
        self.result = None
        self.union_box = (0, 0, 10000000, 10000000)
        self.cli = renderer.find_kicad_cli(config.get("kicad_cli_path") or "")
        self.tmp_dir = tempfile.mkdtemp(prefix="kicad_change_log_")
        self._aff_cache = {}
        self._updating = False

        panel = wx.Panel(self)
        split = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE)
        left_panel = wx.Panel(split)
        right_panel = wx.Panel(split)
        split.SplitVertically(left_panel, right_panel, 360)

        # ---------------- 左侧:变动列表(按图层分组) ----------------
        left = wx.BoxSizer(wx.VERTICAL)
        ver_row = wx.BoxSizer(wx.HORIZONTAL)
        ver_row.Add(wx.StaticText(left_panel, label="A(旧):"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        self.choice_a = wx.Choice(left_panel)
        ver_row.Add(self.choice_a, 1, wx.LEFT, 2)
        ver_row.Add(wx.StaticText(left_panel, label="B(新):"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        self.choice_b = wx.Choice(left_panel)
        ver_row.Add(self.choice_b, 1, wx.LEFT, 2)
        left.Add(ver_row, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)
        self.lbl_stats = wx.StaticText(left_panel, label="统计: -")
        left.Add(self.lbl_stats, 0, wx.EXPAND | wx.LEFT, 4)
        self.tree = wx.TreeCtrl(left_panel, style=wx.TR_HIDE_ROOT | wx.TR_HAS_BUTTONS)
        left.Add(self.tree, 1, wx.EXPAND | wx.ALL, 4)
        left_panel.SetSizer(left)

        # ---------------- 右侧:图层对比图 ----------------
        right = wx.BoxSizer(wx.VERTICAL)
        ctrl_row = wx.BoxSizer(wx.HORIZONTAL)
        ctrl_row.Add(wx.StaticText(right_panel, label="图层:"),
                     0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        self.layer_choice = wx.Choice(right_panel)
        ctrl_row.Add(self.layer_choice, 0, wx.LEFT, 2)
        self.mode_choice = wx.Choice(right_panel,
                                     choices=["并排对比", "红绿叠加", "滑块分割"])
        self.mode_choice.SetSelection(0)
        ctrl_row.Add(self.mode_choice, 0, wx.LEFT, 10)
        self.split_slider = wx.Slider(right_panel, value=50, minValue=0,
                                      maxValue=100,
                                      style=wx.SL_HORIZONTAL | wx.SL_AUTOTICKS)
        ctrl_row.Add(self.split_slider, 1, wx.EXPAND | wx.LEFT, 6)
        right.Add(ctrl_row, 0, wx.EXPAND | wx.ALL, 4)

        self.canvas = CompareCanvas(right_panel)
        self.canvas.on_cursor = self._on_canvas_cursor
        right.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 4)

        self._status_base = "就绪(滚轮缩放 · 左键拖拽平移 · 双击/中键复位)"
        self._unit = "mm"
        self.lbl_status = wx.StaticText(right_panel, label=self._status_base)
        right.Add(self.lbl_status, 0, wx.EXPAND | wx.LEFT, 4)

        legend = wx.BoxSizer(wx.HORIZONTAL)
        for text, colour in (("新增", wx.Colour(60, 220, 80)),
                             ("删除", wx.Colour(255, 60, 60)),
                             ("修改", wx.Colour(255, 200, 0)),
                             ("未变(压暗)", wx.Colour(120, 120, 120))):
            label = wx.StaticText(right_panel, label="■ " + text)
            label.SetForegroundColour(colour)
            legend.Add(label, 0, wx.LEFT | wx.RIGHT, 6)
        right.Add(legend, 0, wx.EXPAND | wx.LEFT, 4)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_fit = wx.Button(right_panel, label="适应窗口")
        self.btn_highlight = wx.Button(right_panel, label="在板上高亮")
        self.btn_export = wx.Button(right_panel, label="导出对比图")
        self.btn_close = wx.Button(right_panel, label="关闭")
        btn_row.Add(self.btn_fit, 0, wx.LEFT, 4)
        btn_row.Add(self.btn_highlight, 0, wx.LEFT, 6)
        btn_row.Add(self.btn_export, 0, wx.LEFT, 6)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(self.btn_close, 0, wx.RIGHT | wx.LEFT, 6)
        right.Add(btn_row, 0, wx.EXPAND | wx.BOTTOM, 6)
        right_panel.SetSizer(right)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(split, 1, wx.EXPAND)
        panel.SetSizer(root_sizer)

        # ---------------- 事件 ----------------
        self.choice_a.Bind(wx.EVT_CHOICE, lambda e: self._on_compare())
        self.choice_b.Bind(wx.EVT_CHOICE, lambda e: self._on_compare())
        self.layer_choice.Bind(wx.EVT_CHOICE, lambda e: self._on_layer_select())
        self.mode_choice.Bind(wx.EVT_CHOICE, lambda e: self._on_mode())
        self.split_slider.Bind(wx.EVT_SLIDER, lambda e: self._on_split())
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_tree_select)
        self.btn_highlight.Bind(wx.EVT_BUTTON, lambda e: self._on_highlight())
        self.btn_export.Bind(wx.EVT_BUTTON, lambda e: self._on_export())
        self.btn_fit.Bind(wx.EVT_BUTTON, lambda e: self.canvas.reset_view())
        self.btn_close.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self.refresh_versions()

    # ------------------------------------------------------------ 版本
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

    def refresh_versions(self):
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
                    if self.initial_a is not None and 0 <= self.initial_a < n:
                        sel_a = self.initial_a
                    else:
                        sel_a = n - 2
                if not (0 <= sel_b < n):
                    if self.initial_b is not None and 0 <= self.initial_b < n:
                        sel_b = self.initial_b
                    else:
                        sel_b = n - 1
                self.choice_a.SetSelection(sel_a)
                self.choice_b.SetSelection(sel_b)
            else:
                self.choice_a.SetSelection(0)
                self.choice_b.SetSelection(0)
        finally:
            self._updating = False
        self._on_compare()

    # ------------------------------------------------------------ 对比
    def _on_compare(self):
        if self._updating:
            return
        paths = self._selected_paths()
        if paths is None or not all(os.path.isfile(p) for p in paths):
            self.changes = []
            self._fill_tree()
            return
        try:
            old = self.model_loader(paths[0])
            new = self.model_loader(paths[1])
            self.changes = diff_engine.diff(old, new)
            self.union_box = diff_engine.union_bbox(old.bbox, new.bbox)
            if self.config.get("units_follow_board"):
                self._unit = units.board_unit()
        except Exception as exc:  # noqa: BLE001
            self.changes = []
            self._set_status("对比失败: %s" % exc)
            self._fill_tree()
            return
        st = diff_engine.stats(self.changes)
        total = sum(sum(d.values()) for d in st.values())
        self.lbl_stats.SetLabel(
            "统计: 共 %d 条(删除 %d / 新增 %d / 替换 %d / 修改 %d)" % (
                total,
                sum(d["removed"] for d in st.values()),
                sum(d["added"] for d in st.values()),
                sum(d["replaced"] for d in st.values()),
                sum(d["modified"] for d in st.values())))
        self._fill_tree()

    def _fill_tree(self):
        self.tree.DeleteAllItems()
        self.item_map = {}
        root = self.tree.AddRoot("变更")
        by_layer = {}
        for ch in self.changes:
            by_layer.setdefault(ch.layer or "其他", []).append(ch)
        self.layers = sorted(by_layer.keys())
        for layer in self.layers:
            items = by_layer[layer]
            layer_item = self.tree.AppendItem(
                root, "%s (%d)" % (board_model.layer_display(layer), len(items)))
            for ch in items:
                label = diff_engine.change_label(ch)
                if ch.change_type == diff_engine.MODIFIED and ch.attrs:
                    label += " · %s变更" % ch.attrs[0].attr
                node = self.tree.AppendItem(
                    layer_item,
                    "%s [%s]" % (label, diff_engine.CHANGE_CN.get(ch.change_type,
                                                                 ch.change_type)))
                self.item_map[node] = ch
        self.tree.ExpandAll()
        # 填充图层下拉
        self._updating = True
        try:
            sel = self.layer_choice.GetSelection()
            self.layer_choice.SetItems(self.layers)
            if not (0 <= sel < len(self.layers)):
                sel = 0 if self.layers else -1
            if sel >= 0:
                self.layer_choice.SetSelection(sel)
        finally:
            self._updating = False
        if self.layers:
            self._on_layer_select()
        else:
            self.canvas.set_result(None)
            self.lbl_status.SetLabel("两个版本之间没有变更")

    def _on_tree_select(self, event):
        node = event.GetItem()
        ch = self.item_map.get(node)
        if ch is None:
            return
        self.current_change = ch
        self.canvas.set_markers([(ch.pos, diff_engine.change_label(ch))])
        if board_highlight is not None:
            try:
                board_highlight.highlight_change(ch)
            except Exception:
                pass
        # 切换到该变更所在图层
        if ch.layer and ch.layer in self.layers:
            idx = self.layers.index(ch.layer)
            if self.layer_choice.GetSelection() != idx:
                self._updating = True
                try:
                    self.layer_choice.SetSelection(idx)
                finally:
                    self._updating = False
                self._on_layer_select()

    # ------------------------------------------------------------ 渲染
    def _on_layer_select(self):
        if self._updating:
            return
        idx = self.layer_choice.GetSelection()
        if idx < 0 or idx >= len(self.layers):
            return
        layer = self.layers[idx]
        paths = self._selected_paths()
        if paths is None:
            return
        self.canvas.set_result(None)
        self.lbl_status.SetLabel("正在渲染图层 %s …" % layer)
        renderer.render_pair_async(
            paths, layer, self.union_box, self.cli, self.tmp_dir,
            int(self.config.get("render_width") or 1600),
            self._on_render_done, self._on_render_error)

    def _on_render_done(self, result):
        if not self:
            return
        self.result = result
        self.canvas.set_result(result)
        if self.current_change is not None:
            self.canvas.set_markers(
                [(self.current_change.pos,
                  diff_engine.change_label(self.current_change))])
        self._set_status("图层 %s 渲染完成" % result["layer"])

    def _set_status(self, text):
        self._status_base = text
        self.lbl_status.SetLabel(text)

    def _on_canvas_cursor(self, board_xy, zoom):
        suffix = "mm" if self._unit == "mm" else "mil"
        text = "%s | 缩放 %.1fx" % (self._status_base, zoom)
        if board_xy is not None:
            text += " | 光标 (%s, %s) %s" % (
                units.fmt_length(int(board_xy[0]), self._unit),
                units.fmt_length(int(board_xy[1]), self._unit), suffix)
        if text != self.lbl_status.GetLabel():
            self.lbl_status.SetLabel(text)

    def _on_render_error(self, message):
        if not self:
            return
        self._set_status("渲染失败: %s" % message[:120])
        wx.MessageBox("图层渲染失败:\n%s\n\n请确认 kicad-cli 可用"
                      "(settings.json 中 kicad_cli_path 可手动指定)。" % message,
                      "变更可视化", wx.OK | wx.ICON_ERROR)

    def _on_mode(self):
        self.canvas.set_mode(self.mode_choice.GetSelection())

    def _on_split(self):
        self.canvas.set_split(self.split_slider.GetValue())

    # ------------------------------------------------------------ 动作
    def _on_highlight(self):
        if self.current_change is None:
            return
        if board_highlight is None:
            return
        found, message = board_highlight.highlight_change_info(
            self.current_change)
        wx.MessageBox(message, "在板上高亮", wx.OK | wx.ICON_INFORMATION)

    def _on_export(self):
        if self.result is None:
            return
        dlg = wx.FileDialog(self, "导出对比图", wildcard="PNG (*.png)|*.png",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        mode = self.mode_choice.GetSelection()
        image = (self.result["img_a"] if mode == MODE_SIDE else
                 self.result["overlay"])
        if image.SaveFile(path, wx.BITMAP_TYPE_PNG):
            self.lbl_status.SetLabel("已导出: %s" % path)
        else:
            wx.MessageBox("导出失败: %s" % path, "导出对比图",
                          wx.OK | wx.ICON_ERROR)

    def _on_close(self, event):
        try:
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass
        if self.on_close is not None:
            self.on_close()
        event.Skip()
