# -*- coding: utf-8 -*-
"""核心引擎单元测试:纯标准库,可用普通 Python 直接运行。

用法:
    python tests/test_diff.py
"""

import os
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_BASE, "..", "kicad_change_log")
sys.path.insert(0, os.path.abspath(_PKG))

import kcl_board_model as board_model
import kcl_diff_engine as diff_engine
import kcl_sexp as sexp
import kcl_units as units


def main():
    failures = []

    def check(name, cond, detail=""):
        if cond:
            print("PASS:", name)
        else:
            failures.append((name, detail))
            print("FAIL:", name, detail)

    # ---- sexp 解析 ----
    nodes = sexp.parse('(foo "a\\"b" (bar 1 2) (baz "c\\nd"))')
    check("sexp 引号转义", nodes[0][1] == 'a"b', repr(nodes))
    check("sexp 换行转义", nodes[0][3][1] == "c\nd", repr(nodes))
    check("sexp 结构", nodes[0][2] == ["bar", "1", "2"], repr(nodes))

    # ---- 板子解析 ----
    old = board_model.load_board(os.path.join(_BASE, "sample_a.kicad_pcb"))
    new = board_model.load_board(os.path.join(_BASE, "sample_b.kicad_pcb"))
    # 3 封装 + 2 走线 + 1 过孔 + 1 区域 + 1 文本 + 4 板框线 = 12
    check("解析 A 元素数", len(old.elements) == 12,
          "实际 %d" % len(old.elements))
    check("解析 B 元素数", len(new.elements) == 12,
          "实际 %d" % len(new.elements))
    check("网络名解析", old.net_name(1) == "GND" and old.net_name(2) == "+5V",
          str(old.nets))
    x1 = old.refs.get("X1")
    check("X1 位号定位", x1 is not None and x1.data["at"] == (11000000, 23000000),
          repr(x1.data if x1 else None))

    # ---- 差异引擎 ----
    changes = diff_engine.diff(old, new)
    labels = [units.format_change_line(c) for c in changes]
    print("---- 变更明细 ----")
    for line in labels:
        print(" ", line)

    check("变更总数", len(changes) == 6, "实际 %d: %s" % (len(changes), labels))

    x1_change = next((c for c in changes
                      if c.kind == board_model.KIND_FOOTPRINT and c.ref == "X1"), None)
    check("X1 变更存在", x1_change is not None)
    if x1_change is not None:
        check("X1 类型为修改", x1_change.change_type == diff_engine.MODIFIED)
        coord = next((a for a in x1_change.attrs if a.attr == "坐标"), None)
        check("X1 坐标属性", coord is not None and coord.old == (11000000, 23000000)
              and coord.new == (111000000, 2222000000), repr(coord))
        check("X1 摘要格式", units.format_change_line(x1_change) ==
              "X1 坐标变更 (11, 23) → (111, 2222)",
              units.format_change_line(x1_change))

    c3_change = next((c for c in changes
                      if c.kind == board_model.KIND_FOOTPRINT and c.ref == "C3"), None)
    check("C3 封装修改", c3_change is not None
          and any(a.attr == "封装" for a in c3_change.attrs), repr(c3_change))

    replaced = next((c for c in changes
                     if c.change_type == diff_engine.REPLACED), None)
    check("R6→R5 替换合并", replaced is not None
          and replaced.ref == "R6→R5"
          and any(a.attr == "替换" for a in replaced.attrs), repr(replaced))
    check("替换库名", replaced is not None
          and replaced.attrs[0].old == "R_0402_1005Metric"
          and replaced.attrs[0].new == "R_0603_1608Metric",
          repr(replaced.attrs if replaced else None))

    seg_change = next((c for c in changes
                       if c.kind == board_model.KIND_SEGMENT), None)
    check("走线起终点变更", seg_change is not None
          and any(a.attr == "起终点" for a in seg_change.attrs), repr(seg_change))
    check("走线网络名", seg_change is not None and seg_change.net == "GND",
          repr(getattr(seg_change, "net", None)))

    via_change = next((c for c in changes
                       if c.kind == board_model.KIND_VIA), None)
    check("过孔位置变更", via_change is not None
          and any(a.attr == "位置" for a in via_change.attrs), repr(via_change))

    text_change = next((c for c in changes
                        if c.kind == board_model.KIND_TEXT), None)
    check("文本变更", text_change is not None
          and any(a.attr == "文本" for a in text_change.attrs), repr(text_change))

    zone_change = next((c for c in changes
                        if c.kind == board_model.KIND_ZONE), None)
    check("区域未变化", zone_change is None, repr(zone_change))

    # ---- 统计与单位 ----
    st = diff_engine.stats(changes)
    mod_total = sum(d["modified"] for d in st.values())
    add_total = sum(d["added"] for d in st.values())
    rem_total = sum(d["removed"] for d in st.values())
    rep_total = sum(d["replaced"] for d in st.values())
    check("统计:修改5", mod_total == 5, str(st))
    check("统计:替换1", rep_total == 1, str(st))
    check("统计:新增0", add_total == 0, str(st))
    check("统计:删除0", rem_total == 0, str(st))

    check("mm 格式化", units.fmt_length(23000000) == "23", units.fmt_length(23000000))
    check("mil 格式化", units.fmt_length(25400000, "mil") == "1000",
          units.fmt_length(25400000, "mil"))

    print()
    if failures:
        print("共 %d 项失败" % len(failures))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
