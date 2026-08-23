# -*- coding: utf-8 -*-
"""快照数据层:维护 snapshots/ 目录、自动/手动快照与板文件监听。

坐标与 hash 逻辑为纯标准库,监听部分依赖 wx(仅在 KiCad 内运行时可用)。
"""

import hashlib
import json
import os
import shutil
import sys
import time

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

try:
    import wx
except ImportError:
    wx = None


def file_hash(path):
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_label(entry):
    stamp = entry.get("time") or 0
    text = time.strftime("%m-%d %H:%M:%S", time.localtime(stamp)) if stamp else ""
    if entry.get("current"):
        return "当前板子 " + text
    note = entry.get("note") or ""
    return (text + " · " + note) if note else text


class SnapshotStore:
    def __init__(self, board_path, config):
        self.board_path = os.path.abspath(board_path)
        self.config = config
        board_dir = os.path.dirname(self.board_path) or "."
        self.snap_dir = os.path.join(board_dir,
                                     config.get("snapshot_dir_name") or "snapshots")
        self.index_path = os.path.join(self.snap_dir, "index.json")
        self.index = {"entries": []}
        self._load()

    # ------------------------------------------------ 索引读写
    def _load(self):
        try:
            with open(self.index_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                self.index = data
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(self.snap_dir, exist_ok=True)
            with open(self.index_path, "w", encoding="utf-8") as fh:
                json.dump(self.index, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------ 快照操作
    def create_snapshot(self, note=""):
        """为当前板文件创建快照;内容与上一条相同则返回 None。"""
        if not os.path.isfile(self.board_path):
            return None
        digest = file_hash(self.board_path)
        entries = self.index.get("entries", [])
        if entries and entries[-1].get("hash") == digest:
            return None
        os.makedirs(self.snap_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        seq = len(entries) + 1
        fname = "snap_%s_%03d.kicad_pcb" % (stamp, seq)
        shutil.copy2(self.board_path, os.path.join(self.snap_dir, fname))
        entry = {"file": fname, "time": time.time(),
                 "note": note or "", "hash": digest}
        entries.append(entry)
        self._save()
        self.prune()
        return entry

    def entries(self):
        return list(self.index.get("entries", []))

    def path_for(self, entry):
        if entry.get("current"):
            return self.board_path
        return os.path.join(self.snap_dir, entry.get("file", ""))

    def last_hash(self):
        entries = self.index.get("entries", [])
        return entries[-1].get("hash") if entries else None

    def prune(self):
        max_count = int(self.config.get("max_snapshots") or 200)
        entries = self.index.get("entries", [])
        if len(entries) <= max_count:
            return
        overflow = entries[: len(entries) - max_count]
        del entries[: len(entries) - max_count]
        for entry in overflow:
            try:
                os.remove(os.path.join(self.snap_dir, entry.get("file", "")))
            except OSError:
                pass
        self._save()


if wx is not None:

    class BoardWatcher(wx.EvtHandler):
        """监听板文件变化并自动生成快照。

        说明:计划阶段考虑过 wx.FileSystemWatcher,但其在 KiCad 内嵌解释器
        中的事件投递存在兼容风险;此处采用轻量定时轮询(比较文件 hash),
        由 wx.Timer 驱动,兼容性与稳定性最好。
        """

        def __init__(self, store, on_snapshot=None):
            super().__init__()
            self.store = store
            self.on_snapshot = on_snapshot or (lambda entry: None)
            self.last_hash = store.last_hash()
            interval = float(store.config.get("poll_interval_s") or 2.0)
            self.timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_tick, self.timer)
            self.timer.Start(max(500, int(interval * 1000)))
            # 尚无快照时先建立基线
            if not store.entries():
                entry = store.create_snapshot("初始快照")
                if entry:
                    self.last_hash = entry.get("hash")

        def _on_tick(self, event):
            if not self.store.config.get("auto_snapshot"):
                return
            digest = file_hash(self.store.board_path)
            if digest is None or digest == self.last_hash:
                return
            self.last_hash = digest
            entry = self.store.create_snapshot("自动快照")
            if entry:
                self.on_snapshot(entry)

        def stop(self):
            try:
                self.timer.Stop()
            except Exception:
                pass

else:

    class BoardWatcher:
        def __init__(self, store, on_snapshot=None):
            self.timer = None

        def stop(self):
            pass
