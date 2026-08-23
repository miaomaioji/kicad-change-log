# -*- coding: utf-8 -*-
"""板子数据模型:解析 .kicad_pcb 并提取可对比元素(纯标准库)。

兼容两种文件格式:
- 旧格式(KiCad ≤9,version < 20260000):坐标以 nm 整数保存
- KiCad 10 新格式(version >= 20260000):坐标以 mm 浮点保存
内部统一换算为 nm。
"""

import os
import re
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import sexp

_VERSION_RE = re.compile(r"\(version\s+(\d+)\)")

# 元素类型
KIND_FOOTPRINT = "footprint"
KIND_SEGMENT = "segment"
KIND_VIA = "via"
KIND_ZONE = "zone"
KIND_TEXT = "gr_text"
KIND_LINE = "gr_line"
KIND_ARC = "gr_arc"
KIND_CIRCLE = "gr_circle"
KIND_RECT = "gr_rect"
KIND_CURVE = "gr_curve"
KIND_DIM = "dimension"

KINDS_CN = {
    KIND_FOOTPRINT: "封装",
    KIND_SEGMENT: "走线",
    KIND_VIA: "过孔",
    KIND_ZONE: "区域",
    KIND_TEXT: "文本",
    KIND_LINE: "图形线",
    KIND_ARC: "圆弧",
    KIND_CIRCLE: "圆",
    KIND_RECT: "矩形",
    KIND_CURVE: "曲线",
    KIND_DIM: "尺寸",
}

LAYER_CN = {
    "F.Cu": "顶层铜",
    "B.Cu": "底层铜",
    "In1.Cu": "内层铜1",
    "In2.Cu": "内层铜2",
    "F.SilkS": "顶层丝印",
    "B.SilkS": "底层丝印",
    "F.Mask": "顶层阻焊",
    "B.Mask": "底层阻焊",
    "F.Paste": "顶层钢网",
    "B.Paste": "底层钢网",
    "F.Fab": "顶层装配",
    "B.Fab": "底层装配",
    "F.CrtYd": "顶层布局",
    "B.CrtYd": "底层布局",
    "Edge.Cuts": "板框",
    "F.Adhes": "顶层胶粘",
    "B.Adhes": "底层胶粘",
    "Margin": "板边距",
    "Dwgs.User": "用户绘图",
    "Cmts.User": "用户注释",
    "Eco1.User": "用户 ECO1",
    "Eco2.User": "用户 ECO2",
}


def layer_display(layer):
    if not layer:
        return "其他"
    cn = LAYER_CN.get(layer)
    return "%s(%s)" % (layer, cn) if cn else layer


class Element:
    """可对比的板子元素。坐标单位均为 nm(与 .kicad_pcb 文件一致)。"""

    __slots__ = ("kind", "uuid", "ref", "name", "layer", "net", "pos", "data")

    def __init__(self, kind, uuid="", ref="", name="", layer="", net="",
                 pos=(0, 0), data=None):
        self.kind = kind
        self.uuid = uuid
        self.ref = ref
        self.name = name
        self.layer = layer
        self.net = net
        self.pos = pos
        self.data = data or {}


# ---------------------------------------------------------------- 提取函数

def _child(node, key):
    return sexp.find(node, key)


def _children(node, key):
    return sexp.find_all(node, key)


def _xy(node, scale=1.0):
    """读取坐标对,按文件格式换算为 nm。"""
    if node is not None and len(node) >= 3:
        return (int(round(sexp.to_float(node[1]) * scale)),
                int(round(sexp.to_float(node[2]) * scale)))
    return (0, 0)


def _num_attr(node, key, index=1, default=0.0, scale=1.0):
    """读取数值属性(mm 格式按 scale 换算为 nm)。"""
    child = sexp.find(node, key)
    if child is not None and len(child) > index:
        return sexp.to_float(child[index]) * scale
    return default


def _rot(node):
    if node is not None and len(node) > 3:
        return sexp.to_float(node[3])
    return 0.0


def _str_child(node, key, index=1, default=""):
    child = _child(node, key)
    if child is not None and len(child) > index:
        return child[index]
    return default


def _uuid(node):
    value = _str_child(node, "uuid")
    if not value:
        value = _str_child(node, "tstamp")
    return value


def _extract_footprint(node, ctx):
    nets = ctx["nets"]
    scale = ctx["scale"]
    libid = node[1] if len(node) > 1 else ""
    at = _child(node, "at")
    x, y = _xy(at, scale)
    rot = _rot(at)
    layer = _str_child(node, "layer")
    side = "B" if layer.startswith("B") else "F"
    uuid = _uuid(node)
    ref = ""
    value = ""
    pad_nets = {}
    for prop in _children(node, "property"):
        if len(prop) > 2:
            if prop[1] == "Reference":
                ref = prop[2]
            elif prop[1] == "Value":
                value = prop[2]
    for pad in _children(node, "pad"):
        if len(pad) > 1:
            num = str(pad[1])
            netname = ""
            nc = _child(pad, "net")
            if nc is not None and len(nc) > 1:
                netname = nets.get(sexp.to_int(nc[1]), "")
            pad_nets[num] = netname
    data = {
        "at": (x, y),
        "rot": rot,
        "side": side,
        "libid": libid,
        "value": value,
        "pad_nets": pad_nets,
    }
    name = ref or (libid.split(":")[-1] if libid else "")
    return Element(KIND_FOOTPRINT, uuid, ref, name, layer, "", (x, y), data)


def _extract_segment(node, ctx):
    nets = ctx["nets"]
    scale = ctx["scale"]
    start = _xy(_child(node, "start"), scale)
    end = _xy(_child(node, "end"), scale)
    width = _num_attr(node, "width", scale=scale)
    layer = _str_child(node, "layer")
    net = nets.get(sexp.to_int(_str_child(node, "net")), "")
    uuid = _uuid(node)
    locked = _child(node, "locked") is not None
    data = {"start": start, "end": end, "width": width, "net": net,
            "locked": locked}
    return Element(KIND_SEGMENT, uuid, "", net, layer, net, start, data)


def _extract_via(node, ctx):
    nets = ctx["nets"]
    scale = ctx["scale"]
    at = _xy(_child(node, "at"), scale)
    size = _num_attr(node, "size", scale=scale)
    drill = _num_attr(node, "drill", scale=scale)
    net = nets.get(sexp.to_int(_str_child(node, "net")), "")
    uuid = _uuid(node)
    layer_list = []
    lc = _child(node, "layers")
    if lc is not None:
        for item in lc[1:]:
            if isinstance(item, list):
                layer_list.extend(item)
            else:
                layer_list.append(item)
    data = {"at": at, "size": size, "drill": drill,
            "layers": tuple(layer_list), "net": net}
    return Element(KIND_VIA, uuid, "", net, layer_list[0] if layer_list else "",
                   net, at, data)


def _extract_zone(node, ctx):
    nets = ctx["nets"]
    scale = ctx["scale"]
    net = nets.get(sexp.to_int(_str_child(node, "net")), "")
    layer = _str_child(node, "layer")
    uuid = _uuid(node)
    pts = []
    poly = _child(node, "polygon")
    if poly is not None:
        pts_node = _child(poly, "pts")
        if pts_node is not None:
            for item in pts_node[1:]:
                if isinstance(item, list) and len(item) >= 3 and item[0] == "xy":
                    pts.append((int(round(sexp.to_float(item[1]) * scale)),
                                int(round(sexp.to_float(item[2]) * scale))))
    pos = (0, 0)
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pos = ((xs[0] + xs[-1]) // 2, (ys[0] + ys[-1]) // 2)
    data = {"net": net, "layer": layer, "pts": pts}
    return Element(KIND_ZONE, uuid, "", net, layer, net, pos, data)


def _extract_text(node, ctx):
    scale = ctx["scale"]
    text = node[1] if len(node) > 1 else ""
    at = _xy(_child(node, "at"), scale)
    rot = _rot(_child(node, "at"))
    layer = _str_child(node, "layer")
    uuid = _uuid(node)
    data = {"text": text, "at": at, "rot": rot}
    return Element(KIND_TEXT, uuid, "", text[:24], layer, "", at, data)


def _extract_graphics(node, ctx, kind):
    scale = ctx["scale"]
    layer = _str_child(node, "layer")
    uuid = _uuid(node)
    pts = []
    for key in ("start", "mid", "end", "center"):
        child = _child(node, key)
        if child is not None:
            pts.append(_xy(child, scale))
    if kind == KIND_CURVE:
        curve = _child(node, "pts")
        if curve is not None:
            pts = []
            for item in curve[1:]:
                if isinstance(item, list) and len(item) >= 3 and item[0] == "xy":
                    pts.append((int(round(sexp.to_float(item[1]) * scale)),
                                int(round(sexp.to_float(item[2]) * scale))))
    width = 0.0
    stroke = _child(node, "stroke")
    if stroke is not None:
        width = sexp.to_float(_str_child(stroke, "width")) * scale
    pos = pts[0] if pts else (0, 0)
    data = {"pts": pts, "width": width, "layer": layer}
    return Element(kind, uuid, "", "", layer, "", pos, data)


def _extract_dimension(node, ctx):
    scale = ctx["scale"]
    layer = _str_child(node, "layer")
    uuid = _uuid(node)
    at = _xy(_child(node, "at"), scale)
    data = {"at": at, "layer": layer}
    return Element(KIND_DIM, uuid, "", "", layer, "", at, data)


_EXTRACTORS = {
    KIND_FOOTPRINT: _extract_footprint,
    "module": _extract_footprint,  # 旧版 KiCad 格式
    KIND_SEGMENT: _extract_segment,
    KIND_VIA: _extract_via,
    KIND_ZONE: _extract_zone,
    KIND_TEXT: _extract_text,
    KIND_LINE: lambda node, ctx: _extract_graphics(node, ctx, KIND_LINE),
    KIND_ARC: lambda node, ctx: _extract_graphics(node, ctx, KIND_ARC),
    KIND_CIRCLE: lambda node, ctx: _extract_graphics(node, ctx, KIND_CIRCLE),
    KIND_RECT: lambda node, ctx: _extract_graphics(node, ctx, KIND_RECT),
    KIND_CURVE: lambda node, ctx: _extract_graphics(node, ctx, KIND_CURVE),
    KIND_DIM: _extract_dimension,
}


def _points_of(el):
    pts = []
    data = el.data or {}
    for key in ("start", "end", "at", "center", "mid"):
        value = data.get(key)
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            pts.append((value[0], value[1]))
    for p in data.get("pts") or []:
        pts.append((p[0], p[1]))
    return pts


def _bbox(pts):
    if not pts:
        return (0, 0, 0, 0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


class BoardModel:
    def __init__(self, elements, nets, bbox):
        self.elements = elements
        self.nets = nets
        self.bbox = bbox
        self.refs = {}
        self.by_uuid = {}
        for el in elements:
            if el.ref and el.ref not in self.refs:
                self.refs[el.ref] = el
            if el.uuid and el.uuid not in self.by_uuid:
                self.by_uuid[el.uuid] = el

    def net_name(self, code):
        return self.nets.get(code, "")


def from_text(text):
    nodes = sexp.parse(text)
    match = _VERSION_RE.search(text)
    is_mm = bool(match) and int(match.group(1)) >= 20260000
    scale = 1e6 if is_mm else 1.0
    root = None
    for node in nodes:
        if isinstance(node, list) and node and node[0] == "kicad_pcb":
            root = node
            break
    children = root[1:] if root is not None else nodes
    nets = {}
    elements = []
    edge_pts = []
    all_pts = []
    ctx = {"nets": nets, "scale": scale}
    for node in children:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if head == "net" and len(node) > 2:
            nets[sexp.to_int(node[1])] = node[2]
            continue
        extractor = _EXTRACTORS.get(head)
        if extractor is None:
            continue
        try:
            el = extractor(node, ctx)
        except Exception:
            continue
        if el is None:
            continue
        elements.append(el)
        pts = _points_of(el)
        if el.layer == "Edge.Cuts":
            edge_pts.extend(pts)
        all_pts.extend(pts)
    bbox = _bbox(edge_pts) if edge_pts else _bbox(all_pts)
    return BoardModel(elements, nets, bbox)


def load_board(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return from_text(text)
