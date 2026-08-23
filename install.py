# -*- coding: utf-8 -*-
"""将插件安装到 KiCad 的 scripting/plugins 目录。

用法:
    python install.py
"""

import os
import shutil

PKG_NAME = "kicad_change_log"


def find_target():
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    root = os.path.join(home, "Documents", "KiCad")
    if os.path.isdir(root):
        versions = sorted(
            [d for d in os.listdir(root)
             if os.path.isdir(os.path.join(root, d))],
            key=lambda s: [int(x) if x.isdigit() else -1 for x in s.split(".")],
            reverse=True)
        for ver in versions:
            plugins_dir = os.path.join(root, ver, "scripting", "plugins")
            if os.path.isdir(plugins_dir):
                return plugins_dir, ver
        if versions:
            plugins_dir = os.path.join(root, versions[0], "scripting", "plugins")
            os.makedirs(plugins_dir, exist_ok=True)
            return plugins_dir, versions[0]
    plugins_dir = os.path.join(root, "10.0", "scripting", "plugins")
    return plugins_dir, "10.0"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, PKG_NAME)
    if not os.path.isdir(src):
        print("未找到插件源码目录: %s" % src)
        return 1
    plugins_dir, version = find_target()
    dst = os.path.join(plugins_dir, PKG_NAME)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print("已安装到: %s (KiCad %s)" % (dst, version))
    print()
    print("使用:打开 KiCad PCB 编辑器 → 菜单「工具 → 外部插件 → 刷新插件」,"
          "再点「项目操作日志与变更可视化」运行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
