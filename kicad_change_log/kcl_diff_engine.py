# -*- coding: utf-8 -*-
"""差异引擎:对比两个 BoardModel,输出结构化变更列表(纯标准库)。"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import kcl_board_model as board_model

ADDED = "added"
REMOVED = "removed"
REPLACED = "replaced"
MODIFIED = "modified"

CHANGE_CN = {ADDED: "新增", REMOVED: "已删除", REPLACED: "替换",
             MODIFIED: "修改"}

_ORDER = {REMOVED: 0, ADDED: 1, REPLACED: 2, MODIFIED: 3}

_REPLACE_DIST_NM = 500000  # 同位置判定阈值(0.5mm)


class AttrChange:
    """一条属性级变更。value_type: coord / length / angle / coordpair / plain。"""

    __slots__ = ("attr", "old", "new", "value_type")

    def __init__(self, attr, old, new, value_type="plain"):
        self.attr = attr
        self.old = old
        self.new = new
        self.value_type = value_type


class Change:
    __slots__ = ("kind", "ref", "name", "change_type", "layer", "net", "pos",
                 "old_uuid", "new_uuid", "attrs", "desc")

    def __init__(self):
        self.kind = ""
        self.ref = ""
        self.name = ""
        self.change_type = ""
        self.layer = ""
        self.net = ""
        self.pos = (0, 0)
        self.old_uuid = ""
        self.new_uuid = ""
        self.attrs = []
        self.desc = []


def change_label(ch):
    """变更条目的显示名:封装显示位号,其余显示类型+名称。"""
    if ch.kind == board_model.KIND_FOOTPRINT:
        return ch.ref or "(无位号)"
    name = ch.name or ch.ref or ""
    cn = board_model.KINDS_CN.get(ch.kind, ch.kind)
    return "%s %s" % (cn, name) if name else cn


# ---------------------------------------------------------------- 属性对比

def _cmp_coord(a, b):
    try:
        return (int(a[0]), int(a[1])) != (int(b[0]), int(b[1]))
    except Exception:
        return str(a) != str(b)


def _cmp_float(a, b, tol=0.001):
    try:
        return abs(float(a) - float(b)) > tol
    except Exception:
        return str(a) != str(b)


def _diff_footprint(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if _cmp_coord(o.get("at", (0, 0)), n.get("at", (0, 0))):
        attrs.append(AttrChange("坐标", o.get("at"), n.get("at"), "coord"))
    if _cmp_float(o.get("rot", 0.0), n.get("rot", 0.0), 0.01):
        attrs.append(AttrChange("旋转", o.get("rot"), n.get("rot"), "angle"))
    if o.get("side") != n.get("side"):
        attrs.append(AttrChange("层面", o.get("side"), n.get("side")))
    if o.get("libid") != n.get("libid"):
        attrs.append(AttrChange("封装", o.get("libid"), n.get("libid")))
    if o.get("value") != n.get("value"):
        attrs.append(AttrChange("值", o.get("value"), n.get("value")))
    if oe.uuid and ne.uuid and oe.uuid != ne.uuid:
        attrs.append(AttrChange("元件替换", oe.uuid[:8], ne.uuid[:8]))
    return attrs


def _diff_segment(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if (_cmp_coord(o.get("start", (0, 0)), n.get("start", (0, 0)))
            or _cmp_coord(o.get("end", (0, 0)), n.get("end", (0, 0)))):
        attrs.append(AttrChange("起终点",
                                (o.get("start"), o.get("end")),
                                (n.get("start"), n.get("end")), "coordpair"))
    if _cmp_float(o.get("width", 0.0), n.get("width", 0.0)):
        attrs.append(AttrChange("线宽", o.get("width"), n.get("width"), "length"))
    if o.get("layer") != n.get("layer"):
        attrs.append(AttrChange("层", o.get("layer"), n.get("layer")))
    if o.get("net") != n.get("net"):
        attrs.append(AttrChange("网络", o.get("net") or "(无)", n.get("net") or "(无)"))
    return attrs


def _diff_via(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if _cmp_coord(o.get("at", (0, 0)), n.get("at", (0, 0))):
        attrs.append(AttrChange("位置", o.get("at"), n.get("at"), "coord"))
    if _cmp_float(o.get("size", 0.0), n.get("size", 0.0)):
        attrs.append(AttrChange("直径", o.get("size"), n.get("size"), "length"))
    if _cmp_float(o.get("drill", 0.0), n.get("drill", 0.0)):
        attrs.append(AttrChange("钻孔", o.get("drill"), n.get("drill"), "length"))
    if tuple(o.get("layers") or ()) != tuple(n.get("layers") or ()):
        attrs.append(AttrChange("层对", "/".join(o.get("layers") or ()),
                                "/".join(n.get("layers") or ())))
    if o.get("net") != n.get("net"):
        attrs.append(AttrChange("网络", o.get("net") or "(无)", n.get("net") or "(无)"))
    return attrs


def _diff_zone(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if o.get("net") != n.get("net"):
        attrs.append(AttrChange("网络", o.get("net") or "(无)", n.get("net") or "(无)"))
    if o.get("layer") != n.get("layer"):
        attrs.append(AttrChange("层", o.get("layer"), n.get("layer")))
    op = [tuple(p) for p in o.get("pts") or []]
    np = [tuple(p) for p in n.get("pts") or []]
    if len(op) != len(np):
        attrs.append(AttrChange("轮廓", "%d 个顶点" % len(op),
                                "%d 个顶点" % len(np)))
    elif op != np:
        attrs.append(AttrChange("轮廓", "原轮廓", "新轮廓"))
    return attrs


def _diff_text(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if o.get("text") != n.get("text"):
        attrs.append(AttrChange("文本", o.get("text"), n.get("text")))
    if _cmp_coord(o.get("at", (0, 0)), n.get("at", (0, 0))):
        attrs.append(AttrChange("位置", o.get("at"), n.get("at"), "coord"))
    if _cmp_float(o.get("rot", 0.0), n.get("rot", 0.0), 0.01):
        attrs.append(AttrChange("旋转", o.get("rot"), n.get("rot"), "angle"))
    if o.get("layer") != n.get("layer"):
        attrs.append(AttrChange("层", o.get("layer"), n.get("layer")))
    return attrs


def _diff_graphics(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    op = o.get("pts") or []
    np = n.get("pts") or []
    if [tuple(p) for p in op] != [tuple(p) for p in np]:
        if op and np and _cmp_coord(op[0], np[0]):
            attrs.append(AttrChange("位置", op[0], np[0], "coord"))
        elif op or np:
            attrs.append(AttrChange("形状", "原图形", "新图形"))
    if _cmp_float(o.get("width", 0.0), n.get("width", 0.0)):
        attrs.append(AttrChange("线宽", o.get("width"), n.get("width"), "length"))
    if o.get("layer") != n.get("layer"):
        attrs.append(AttrChange("层", o.get("layer"), n.get("layer")))
    return attrs


def _diff_dimension(oe, ne):
    attrs = []
    o, n = oe.data, ne.data
    if _cmp_coord(o.get("at", (0, 0)), n.get("at", (0, 0))):
        attrs.append(AttrChange("位置", o.get("at"), n.get("at"), "coord"))
    if o.get("layer") != n.get("layer"):
        attrs.append(AttrChange("层", o.get("layer"), n.get("layer")))
    return attrs


_GENERIC_DIFFS = {
    board_model.KIND_SEGMENT: _diff_segment,
    board_model.KIND_VIA: _diff_via,
    board_model.KIND_ZONE: _diff_zone,
    board_model.KIND_TEXT: _diff_text,
    board_model.KIND_LINE: _diff_graphics,
    board_model.KIND_ARC: _diff_graphics,
    board_model.KIND_CIRCLE: _diff_graphics,
    board_model.KIND_RECT: _diff_graphics,
    board_model.KIND_CURVE: _diff_graphics,
    board_model.KIND_DIM: _diff_dimension,
}


def _describe(el):
    """新增/删除元素的描述行列表:(名称, 值, value_type)。"""
    out = []
    data = el.data or {}
    if el.kind == board_model.KIND_FOOTPRINT:
        out.append(("封装", data.get("libid", ""), "plain"))
        out.append(("位置", el.pos, "coord"))
        if data.get("value"):
            out.append(("值", data.get("value"), "plain"))
        out.append(("层", el.layer, "plain"))
    elif el.kind == board_model.KIND_SEGMENT:
        out.append(("起点", data.get("start", (0, 0)), "coord"))
        out.append(("终点", data.get("end", (0, 0)), "coord"))
        out.append(("线宽", data.get("width", 0.0), "length"))
        out.append(("网络", el.net or "(无)", "plain"))
    elif el.kind == board_model.KIND_VIA:
        out.append(("位置", el.pos, "coord"))
        out.append(("直径", data.get("size", 0.0), "length"))
        out.append(("钻孔", data.get("drill", 0.0), "length"))
        out.append(("网络", el.net or "(无)", "plain"))
    elif el.kind == board_model.KIND_ZONE:
        out.append(("网络", el.net or "(无)", "plain"))
        out.append(("层", el.layer, "plain"))
        out.append(("顶点数", len(data.get("pts") or []), "plain"))
    elif el.kind == board_model.KIND_TEXT:
        out.append(("文本", data.get("text", ""), "plain"))
        out.append(("位置", el.pos, "coord"))
        out.append(("层", el.layer, "plain"))
    else:
        if el.layer:
            out.append(("层", el.layer, "plain"))
        if el.pos != (0, 0):
            out.append(("位置", el.pos, "coord"))
    return out


# ---------------------------------------------------------------- 匹配与汇总

def _make(ctype, oe, ne, attrs=None):
    ch = Change()
    primary = ne if ne is not None else oe
    ch.kind = primary.kind
    ch.ref = primary.ref
    ch.name = primary.name
    ch.change_type = ctype
    ch.layer = primary.layer
    ch.net = primary.net
    ch.pos = primary.pos
    ch.old_uuid = oe.uuid if oe is not None else ""
    ch.new_uuid = ne.uuid if ne is not None else ""
    ch.attrs = attrs or []
    if ctype != MODIFIED:
        ch.desc = _describe(primary)
    return ch


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _desc_libid(change):
    """从 desc 中取封装库名(去库前缀)。"""
    for key, value, _vtype in change.desc:
        if key == "封装" and isinstance(value, str):
            return value.split(":")[-1] if ":" in value else value
    return ""


def _merge_replaces(changes):
    """同位置(≤0.5mm)且同层的「删除+新增」合并为一条「替换」。"""
    removed_fp = [c for c in changes if c.change_type == REMOVED
                  and c.kind == board_model.KIND_FOOTPRINT]
    added_fp = [c for c in changes if c.change_type == ADDED
                and c.kind == board_model.KIND_FOOTPRINT]
    if not removed_fp or not added_fp:
        return changes
    consumed = set()
    merged = []
    for rc in removed_fp:
        if rc in consumed:
            continue
        for ac in added_fp:
            if ac in consumed:
                continue
            if rc.layer != ac.layer or _dist(rc.pos, ac.pos) > _REPLACE_DIST_NM:
                continue
            ch = Change()
            ch.kind = board_model.KIND_FOOTPRINT
            ch.ref = "%s→%s" % (rc.ref or "(无)", ac.ref or "(无)")
            ch.name = ch.ref
            ch.change_type = REPLACED
            ch.layer = ac.layer
            ch.net = ac.net
            ch.pos = ac.pos
            ch.old_uuid = rc.old_uuid
            ch.new_uuid = ac.new_uuid
            ch.attrs = [AttrChange("替换", _desc_libid(rc), _desc_libid(ac))]
            merged.append(ch)
            consumed.add(rc)
            consumed.add(ac)
            break
    if not merged:
        return changes
    return [c for c in changes if c not in consumed] + merged


def diff(old, new):
    """对比两个 BoardModel,返回 Change 列表。

    匹配策略:封装先按位号匹配,其余元素按 uuid 匹配。
    """
    changes = []

    # 封装:按位号匹配(替换元件不拆成删除+新增)
    for ref, oe in old.refs.items():
        ne = new.refs.get(ref)
        if ne is None:
            changes.append(_make(REMOVED, oe, None))
        else:
            attrs = _diff_footprint(oe, ne)
            if attrs:
                changes.append(_make(MODIFIED, oe, ne, attrs))
    for ref, ne in new.refs.items():
        if ref in old.refs:
            continue
        changes.append(_make(ADDED, None, ne))

    # 其余元素:按 uuid 匹配
    old_map = {e.uuid: e for e in old.elements
               if e.kind != board_model.KIND_FOOTPRINT and e.uuid}
    new_map = {e.uuid: e for e in new.elements
               if e.kind != board_model.KIND_FOOTPRINT and e.uuid}
    for uuid, oe in old_map.items():
        ne = new_map.get(uuid)
        if ne is None:
            changes.append(_make(REMOVED, oe, None))
        else:
            attrs = _diff_generic(oe, ne)
            if attrs:
                changes.append(_make(MODIFIED, oe, ne, attrs))
    for uuid, ne in new_map.items():
        if uuid not in old_map:
            changes.append(_make(ADDED, None, ne))

    # 同位置删除+新增 → 替换
    changes = _merge_replaces(changes)

    changes.sort(key=lambda c: (_ORDER.get(c.change_type, 9), c.kind, c.ref or c.name))
    return changes


def _diff_generic(oe, ne):
    fn = _GENERIC_DIFFS.get(oe.kind)
    return fn(oe, ne) if fn else []


def stats(changes):
    """按元素类型聚合统计:{kind: {added, removed, replaced, modified}}。"""
    agg = {}
    for ch in changes:
        d = agg.setdefault(ch.kind, {"added": 0, "removed": 0,
                                    "replaced": 0, "modified": 0})
        d[ch.change_type] += 1
    return agg


def union_bbox(a, b):
    """合并两个板框(用于校准标记定位与渲染对齐基准)。"""
    def valid(bb):
        return bb and (bb[2] - bb[0]) > 0 and (bb[3] - bb[1]) > 0
    if valid(a) and valid(b):
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
    if valid(a):
        return tuple(a)
    if valid(b):
        return tuple(b)
    return (0, 0, 10000000, 10000000)
