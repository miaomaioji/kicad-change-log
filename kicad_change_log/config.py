# -*- coding: utf-8 -*-
"""插件配置(纯标准库)。"""

import json
import os

# 插件版本号(与 build_pcm.py 中 VERSION 保持一致)
VERSION = "1.1.0"

_DEFAULTS = {
    # 保存文件后自动生成快照
    "auto_snapshot": True,
    # 快照目录名(位于板文件所在目录下)
    "snapshot_dir_name": "snapshots",
    # 最多保留的快照数量
    "max_snapshots": 200,
    # 监听轮询间隔(秒)
    "poll_interval_s": 2.0,
    # kicad-cli 可执行文件路径(留空自动查找)
    "kicad_cli_path": "",
    # 图层图渲染宽度(像素)
    "render_width": 1600,
    # 日志坐标单位跟随板子显示设置
    "units_follow_board": True,
}


def plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


class Config:
    def __init__(self, path=None):
        self.path = path or os.path.join(plugin_dir(), "settings.json")
        self.data = dict(_DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                for key in _DEFAULTS:
                    if key in loaded:
                        self.data[key] = loaded[key]
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key):
        return self.data.get(key, _DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()
