# -*- coding: utf-8 -*-
"""临时探测脚本:查看 kicad-cli svg 输出格式(用于校准解析)。"""

import os
import subprocess
import sys
import tempfile

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_BASE, "..", "kicad_change_log")
sys.path.insert(0, os.path.abspath(_PKG))

import kcl_renderer as renderer

CLI = renderer.find_kicad_cli("") or "kicad-cli"
TMP = tempfile.mkdtemp(prefix="kcl_probe_")
print("TMP:", TMP)

sample = os.path.join(_BASE, "..", "tests", "sample_a.kicad_pcb")
bbox = (0, 0, 100000000, 60000000)

# 1) 注入校准标记并导出 User.9 层
calib = os.path.join(TMP, "calib.kicad_pcb")
pts = renderer._inject_markers(sample, calib, bbox)
print("标记板坐标:", pts)

calib_svg = os.path.join(TMP, "calib.svg")
cmd = [CLI, "pcb", "export", "svg", "-o", calib_svg,
       "--layers", renderer.CALIB_LAYER, "--mode-single",
       "--page-size-mode", "2", "--exclude-drawing-sheet", calib]
proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
print("导出 User.9 返回码:", proc.returncode, proc.stderr.decode()[:300])
with open(calib_svg, "r", encoding="utf-8") as fh:
    svg_text = fh.read()
print("---- User.9 SVG 前 1500 字符 ----")
print(svg_text[:1500])
print("---- 尾部 500 字符 ----")
print(svg_text[-500:])

# 2) 导出 F.Cu 层,查看 viewBox
cu_svg = os.path.join(TMP, "cu.svg")
cmd2 = [CLI, "pcb", "export", "svg", "-o", cu_svg,
        "--layers", "F.Cu", "--mode-single",
        "--page-size-mode", "2", "--exclude-drawing-sheet", sample]
proc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
print("导出 F.Cu 返回码:", proc2.returncode, proc2.stderr.decode()[:300])
with open(cu_svg, "r", encoding="utf-8") as fh:
    cu_text = fh.read()
print("---- F.Cu SVG 前 600 字符 ----")
print(cu_text[:600])
