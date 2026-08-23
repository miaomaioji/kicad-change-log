# -*- coding: utf-8 -*-
"""端到端渲染验证:用 KiCad 自带 Python 运行真实 kicad-cli 渲染管线。

用法(必须用 KiCad 10 自带 Python):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests\\e2e_render.py
"""

import os
import sys
import tempfile

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_BASE, "..", "kicad_change_log")
sys.path.insert(0, os.path.abspath(_PKG))

import board_model
import diff_engine
import renderer


def main():
    cli = renderer.find_kicad_cli("")
    assert cli, "未找到 kicad-cli"
    print("kicad-cli:", cli)

    sample_a = os.path.join(_BASE, "e2e_a.kicad_pcb")
    sample_b = os.path.join(_BASE, "e2e_b.kicad_pcb")
    old = board_model.load_board(sample_a)
    new = board_model.load_board(sample_b)
    bbox = diff_engine.union_bbox(old.bbox, new.bbox)
    print("board bbox (nm):", bbox)

    # 校验 mm 格式解析:X1 在 A 版应为 (11, 23) mm
    x1_a = old.refs.get("X1")
    assert x1_a is not None and x1_a.data["at"] == (11000000, 23000000), \
        "X1 A 版解析错误: %s" % (x1_a.data if x1_a else None)
    print("mm 格式解析验证: X1 A 版 @ (11, 23) mm ✓")

    out_dir = os.path.join(_BASE, "..", "dist", "preview")
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="kcl_e2e_")

    # 只渲染有变更的图层
    changes = diff_engine.diff(old, new)
    layers = sorted({c.layer for c in changes})
    print("有变更的图层:", layers)

    width = 1200
    for layer in layers:
        result = renderer.render_pair((sample_a, sample_b), layer, bbox,
                                      cli, tmp, width=width)
        aff = result["aff"]
        wa = result["img_a"].GetWidth()
        ha = result["img_a"].GetHeight()
        print("图层 %s: 尺寸 %dx%d, 仿射 (ax=%.6g, cx=%.1f, ay=%.6g, cy=%.1f)"
              % (layer, wa, ha, aff[0], aff[1], aff[2], aff[3]))

        # 校验:X1 旧位置 (11, 23) mm 应映射到图像内部
        x1_old = (11000000, 23000000)
        px = aff[0] * x1_old[0] + aff[1]
        py = aff[2] * x1_old[1] + aff[3]
        assert 0 <= px < wa and 0 <= py < ha, \
            "X1 映射超出图像: %s -> (%s, %s)" % (x1_old, px, py)
        print("  X1 旧位置映射到像素 (%.1f, %.1f) ✓" % (px, py))

        safe = layer.replace(".", "_")
        result["img_a"].SaveFile(os.path.join(out_dir, "%s_a.png" % safe),
                                 wx.BITMAP_TYPE_PNG)
        result["aligned"].SaveFile(os.path.join(out_dir, "%s_b_aligned.png" % safe),
                                   wx.BITMAP_TYPE_PNG)
        result["overlay"].SaveFile(os.path.join(out_dir, "%s_overlay.png" % safe),
                                   wx.BITMAP_TYPE_PNG)

    print("预览图已输出到:", os.path.abspath(out_dir))
    print("全部通过")


if __name__ == "__main__":
    import wx
    app = wx.App()
    try:
        main()
    finally:
        app.Destroy()
