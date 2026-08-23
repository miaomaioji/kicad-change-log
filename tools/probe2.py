# -*- coding: utf-8 -*-
"""对照实验:用 pcbnew API 生成标准板文件,对比 SVG 导出行为。"""

import os
import subprocess
import sys
import tempfile

import pcbnew

CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
TMP = tempfile.mkdtemp(prefix="kcl_probe2_")
print("TMP:", TMP)

# ---- 1) 检查页面设置(用 API 生成的板) ----
# 注:手写样例板文件在 KiCad 10 加载时触发整数溢出,因此跳过,
# 直接用 API 生成标准板做对照。

# ---- 2) 用 API 生成标准板并导出 SVG ----
board = pcbnew.NewBoard("")
board.SetCopperLayerCount(2)
# 板框
for start, end in (((0, 0), (100, 0)), ((100, 0), (100, 60)),
                   ((100, 60), (0, 60)), ((0, 60), (0, 0))):
    line = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    line.SetStart(pcbnew.VECTOR2I(int(start[0] * 1e6), int(start[1] * 1e6)))
    line.SetEnd(pcbnew.VECTOR2I(int(end[0] * 1e6), int(end[1] * 1e6)))
    line.SetLayer(pcbnew.Edge_Cuts)
    board.Add(line)
# 校准标记
for cx in (2.0, 98.0):
    circle = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE)
    circle.SetCenter(pcbnew.VECTOR2I(int(cx * 1e6), int(30 * 1e6)))
    circle.SetEnd(pcbnew.VECTOR2I(int((cx + 0.2) * 1e6), int(30 * 1e6)))
    circle.SetWidth(int(0.15 * 1e6))
    circle.SetLayer(pcbnew.User_9)
    board.Add(circle)

path = os.path.join(TMP, "api_board.kicad_pcb")
pcbnew.SaveBoard(path, board)
print("API 板已保存:", path)
ps = board.GetPageSettings()
print("页面对象方法:", [m for m in dir(ps) if "Size" in m or "Get" in m][:20])

svg = os.path.join(TMP, "api_user9.svg")
cmd = [CLI, "pcb", "export", "svg", "-o", svg,
       "--layers", "User.9", "--mode-single",
       "--page-size-mode", "2", "--exclude-drawing-sheet", path]
proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
print("导出返回码:", proc.returncode, proc.stderr.decode()[:300])
with open(svg, "r", encoding="utf-8") as fh:
    text = fh.read()
print("---- API 板 User.9 SVG 前 1200 字符 ----")
print(text[:1200])
print("---- 文件中的 gr_circle 写法 ----")
with open(path, "r", encoding="utf-8") as fh:
    board_text = fh.read()
i = board_text.find("gr_circle")
print(board_text[max(0, i - 120): i + 400])
print("---- 板文件头部 800 字符 ----")
print(board_text[:800])
