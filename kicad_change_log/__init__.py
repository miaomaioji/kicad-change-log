# -*- coding: utf-8 -*-
"""KiCad ActionPlugin 注册:项目操作日志与变更可视化。

安装到 KiCad 的 scripting/plugins/kicad_change_log/ 目录后,
在 PCB 编辑器菜单「工具 → 外部插件」中运行。
"""

import os
import sys

import pcbnew


class ChangeLogPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "项目操作日志与变更可视化"
        self.category = "检查"
        self.description = ("记录项目快照,以变动日志与图层对比图"
                            "可视化每次改动(新增/删除/修改)")
        self.show_toolbar_button = True
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon = os.path.join(base_dir, "icon.png")
        if not os.path.isfile(icon):
            icon = os.path.join(base_dir, "icon.svg")
        self.icon_file_name = icon

    def Run(self):
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
        import plugin
        plugin.run()


ChangeLogPlugin().register()
