# -*- coding: utf-8 -*-
"""用 pcbnew API 生成 KiCad 10 原生格式的端到端样例板(A/B 两个版本)。

用法(必须用 KiCad 10 自带 Python):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests\\make_sample_boards.py
"""

import os

import pcbnew

_BASE = os.path.dirname(os.path.abspath(__file__))


def _mm(value):
    return int(round(value * 1e6))


def _build():
    board = pcbnew.NewBoard("")
    board.SetCopperLayerCount(2)
    for name in ("GND", "+5V"):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)

    def netcode(name):
        net = board.FindNet(name)
        return net.GetNetCode() if net else 0

    # 板框 100x60mm
    edges = (((0, 0), (100, 0)), ((100, 0), (100, 60)),
             ((100, 60), (0, 60)), ((0, 60), (0, 0)))
    for (x1, y1), (x2, y2) in edges:
        line = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        line.SetStart(pcbnew.VECTOR2I(_mm(x1), _mm(y1)))
        line.SetEnd(pcbnew.VECTOR2I(_mm(x2), _mm(y2)))
        line.SetLayer(pcbnew.Edge_Cuts)
        board.Add(line)

    def add_footprint(ref, value, libid, x, y, rot=0.0):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetValue(value)
        if hasattr(fp, "SetFPIDAsString"):
            fp.SetFPIDAsString(libid)
        elif hasattr(fp, "SetLibId"):
            fp.SetLibId(pcbnew.LIB_ID(libid))
        else:
            fp.SetFPID(pcbnew.LIB_ID(libid))
        fp.SetPosition(pcbnew.VECTOR2I(_mm(x), _mm(y)))
        fp.SetOrientationDegrees(rot)
        fp.SetLayer(pcbnew.F_Cu)
        board.Add(fp)
        return fp

    def add_track(x1, y1, x2, y2, width, netname):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pcbnew.VECTOR2I(_mm(x1), _mm(y1)))
        tr.SetEnd(pcbnew.VECTOR2I(_mm(x2), _mm(y2)))
        tr.SetWidth(_mm(width))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNetCode(netcode(netname))
        board.Add(tr)

    def add_via(x, y, size, drill, netname):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(_mm(x), _mm(y)))
        via.SetWidth(_mm(size))
        via.SetDrill(_mm(drill))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(netcode(netname))
        board.Add(via)

    def add_text(text, x, y):
        item = pcbnew.PCB_TEXT(board)
        item.SetText(text)
        item.SetPosition(pcbnew.VECTOR2I(_mm(x), _mm(y)))
        item.SetLayer(pcbnew.F_SilkS)
        board.Add(item)

    # ---- A 版内容 ----
    add_footprint("X1", "10k", "Resistor_SMD:R_0805_2012Metric", 11, 23)
    add_footprint("C3", "100n", "Capacitor_SMD:C_0603_1608Metric", 22, 30, 90)
    add_footprint("R6", "1k", "Resistor_SMD:R_0402_1005Metric", 33, 40)
    add_track(5, 5, 50, 5, 0.25, "GND")
    add_track(5, 10, 5, 40, 0.3, "+5V")
    add_via(20, 20, 0.8, 0.4, "GND")
    add_text("REV-A", 30, 55)
    return board


def _mutate(board):
    """原地修改为 B 版:移动 X1、替换 C3 封装、R6→R5、移动走线/过孔、改文本。"""
    x1 = board.FindFootprintByReference("X1")
    x1.SetPosition(pcbnew.VECTOR2I(_mm(45), _mm(32)))
    c3 = board.FindFootprintByReference("C3")
    if hasattr(c3, "SetFPIDAsString"):
        c3.SetFPIDAsString("Capacitor_SMD:C_0805_2012Metric")
    else:
        c3.SetFPID(pcbnew.LIB_ID("Capacitor_SMD:C_0805_2012Metric"))
    r6 = board.FindFootprintByReference("R6")
    board.Remove(r6)
    r5 = pcbnew.FOOTPRINT(board)
    r5.SetReference("R5")
    r5.SetValue("4.7k")
    if hasattr(r5, "SetFPIDAsString"):
        r5.SetFPIDAsString("Resistor_SMD:R_0603_1608Metric")
    else:
        r5.SetFPID(pcbnew.LIB_ID("Resistor_SMD:R_0603_1608Metric"))
    r5.SetPosition(pcbnew.VECTOR2I(_mm(33), _mm(40)))
    r5.SetLayer(pcbnew.F_Cu)
    board.Add(r5)

    for item in board.GetTracks():
        name = type(item).__name__
        if name == "PCB_VIA" and item.GetNetname() == "GND":
            item.SetPosition(pcbnew.VECTOR2I(_mm(21), _mm(20)))
        elif name == "PCB_TRACK" and item.GetNetname() == "GND":
            item.SetStart(pcbnew.VECTOR2I(_mm(5), _mm(8)))
            item.SetEnd(pcbnew.VECTOR2I(_mm(50), _mm(8)))
    for drawing in board.GetDrawings():
        if type(drawing).__name__ == "PCB_TEXT":
            drawing.SetText("REV-B")


def main():
    board_a = _build()
    path_a = os.path.join(_BASE, "e2e_a.kicad_pcb")
    pcbnew.SaveBoard(path_a, board_a)
    print("已生成:", path_a)
    _mutate(board_a)
    path_b = os.path.join(_BASE, "e2e_b.kicad_pcb")
    pcbnew.SaveBoard(path_b, board_a)
    print("已生成:", path_b)


if __name__ == "__main__":
    main()
