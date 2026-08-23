# -*- coding: utf-8 -*-
"""数值与单位格式化(纯标准库;运行时可选读取 pcbnew 单位设置)。"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import diff_engine

NM_PER_MM = 1000000.0
NM_PER_MIL = 25400.0


def board_unit():
    """读取当前板子显示单位:1=mm, 0/2=mil/英寸。"""
    try:
        import pcbnew
        value = int(pcbnew.GetUserUnits())
        if value == 1:
            return "mm"
        if value in (0, 2):
            return "mil"
    except Exception:
        pass
    return "mm"


def fmt_length(nm, unit="mm", decimals=None):
    try:
        nm = float(nm)
    except (TypeError, ValueError):
        return str(nm)
    if decimals is None:
        decimals = 2 if unit == "mil" else 4
    factor = NM_PER_MIL if unit == "mil" else NM_PER_MM
    fmt = "%%.%df" % decimals
    s = fmt % round(nm / factor, decimals)
    return s.rstrip("0").rstrip(".")


def fmt_coord(xy, unit="mm", decimals=None):
    if not isinstance(xy, (tuple, list)) or len(xy) < 2:
        return "—"
    return "(%s, %s)" % (fmt_length(xy[0], unit, decimals),
                         fmt_length(xy[1], unit, decimals))


def fmt_value(value, value_type="plain", unit="mm", decimals=None):
    if value is None or value == "":
        return "—"
    if value_type == "coord":
        return fmt_coord(value, unit, decimals)
    if value_type == "length":
        suffix = "mil" if unit == "mil" else "mm"
        return "%s%s" % (fmt_length(value, unit, decimals), suffix)
    if value_type == "angle":
        try:
            return "%g°" % float(value)
        except (TypeError, ValueError):
            return str(value)
    if value_type == "coordpair":
        if not isinstance(value, (tuple, list)) or len(value) < 2:
            return str(value)
        return "%s → %s" % (fmt_coord(value[0], unit, decimals),
                            fmt_coord(value[1], unit, decimals))
    return str(value)


def fmt_attr(attr_change, unit="mm", decimals=None):
    return "%s → %s" % (fmt_value(attr_change.old, attr_change.value_type, unit,
                                  decimals),
                        fmt_value(attr_change.new, attr_change.value_type, unit,
                                  decimals))


def shorten(text, max_len=40):
    """超长文本截断并加省略号。"""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def format_change_line(change, unit="mm"):
    """生成一行摘要,如「X1 坐标变更 (11, 23) → (111, 2222)」。"""
    label = diff_engine.change_label(change)
    type_cn = diff_engine.CHANGE_CN.get(change.change_type, change.change_type)
    if change.change_type != diff_engine.MODIFIED or not change.attrs:
        return "%s %s" % (label, type_cn)
    first = change.attrs[0]
    line = "%s %s变更 %s" % (label, first.attr, fmt_attr(first, unit))
    if len(change.attrs) > 1:
        line += " 等%d项" % len(change.attrs)
    return line


def format_first_attr(change, unit="mm", decimals=None):
    """首条属性变更的精简描述,如「坐标 (142.88, 57.15) → (125.33, 136.17)」。"""
    first = change.attrs[0]
    line = "%s %s" % (first.attr, fmt_attr(first, unit, decimals))
    if len(change.attrs) > 1:
        line += " 等%d项" % len(change.attrs)
    return line


def format_desc_line(change, unit="mm", decimals=None):
    """新增/删除元素的描述行,如「封装 SW_Choc_V2 · 位置 (176.21, 95.23)」。"""
    parts = []
    for key, value, vtype in change.desc:
        if vtype == "plain" and isinstance(value, str) and ":" in value:
            value = value.split(":")[-1]
        parts.append("%s %s" % (key, fmt_value(value, vtype, unit, decimals)))
    return " · ".join(parts)
