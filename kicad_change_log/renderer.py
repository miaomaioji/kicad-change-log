# -*- coding: utf-8 -*-
"""图层图渲染封装(SVG 管线,适配 KiCad 10)。

KiCad 10 的 `kicad-cli pcb render` 已改为 3D 渲染且不再支持 --layers,
因此分层图改用 `kicad-cli pcb export svg --layers <层>` 导出,
再用 wx.BitmapBundle 光栅化为位图。

对齐原理:向板文件注入两个已知板坐标的校准标记(导出后不保留),
通过标记在图像中的像素质心直接求解「板坐标 → 像素」仿射变换,
两版图像即可像素级对齐,支持红绿叠加对比。
"""

import os
import re
import shutil
import subprocess
import sys
import threading

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

try:
    import wx
except ImportError:
    wx = None

# 校准标记所在图层与标记半径(nm)
CALIB_LAYER = "User.9"
CALIB_MARKER_R = 200000

_ALPHA_ON = 40          # alpha 大于该值视为有内容
_VERSION_RE = re.compile(r"\(version\s+(\d+)\)")
_FILL_RE = re.compile(r"\(fill\s+(\w+)\)")


def find_kicad_cli(config_path=""):
    """查找 kicad-cli 可执行文件。"""
    candidates = []
    if config_path:
        candidates.append(config_path)
    found = shutil.which("kicad-cli")
    if found:
        candidates.append(found)
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            kroot = os.path.join(base, "KiCad")
            if not os.path.isdir(kroot):
                continue
            try:
                versions = sorted(os.listdir(kroot), reverse=True)
            except OSError:
                continue
            for ver in versions:
                candidates.append(os.path.join(kroot, ver, "bin", "kicad-cli.exe"))
    else:
        candidates += ["/usr/bin/kicad-cli", "/usr/local/bin/kicad-cli"]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    return found


def _run(cmd):
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=flags)
    if proc.returncode != 0:
        raise RuntimeError("kicad-cli 失败: "
                           + proc.stderr.decode(errors="ignore")[:500])


def _file_version(path):
    """读取板文件格式版本号,未找到返回 0。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read(4096)
        match = _VERSION_RE.search(text)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def _file_is_mm(path):
    """KiCad 10(version >= 20260000)原生以 mm 浮点保存坐标。"""
    return _file_version(path) >= 20260000


def _fill_token(path):
    """读取板文件中的 fill 写法(no / none),保持注入标记风格一致。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        match = _FILL_RE.search(text)
        return match.group(1) if match else "no"
    except Exception:
        return "no"


# ---------------------------------------------------------------- 导出与光栅化

def export_layer_svg(board_file, layer, out_svg, cli):
    """导出指定图层为 SVG(板区域模式、无图框)。"""
    if not cli:
        raise RuntimeError("未找到 kicad-cli,请在 settings.json 中配置 kicad_cli_path")
    out_dir = os.path.dirname(out_svg)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    cmd = [cli, "pcb", "export", "svg",
           "-o", out_svg,
           "--layers", layer,
           "--mode-single",
           "--page-size-mode", "2",
           "--exclude-drawing-sheet",
           board_file]
    _run(cmd)
    if not os.path.isfile(out_svg):
        raise RuntimeError("导出未生成输出: %s" % layer)
    return out_svg


def rasterize_svg(svg_path, width, height):
    """把 SVG 光栅化为指定尺寸的 wx.Image(带 alpha 通道)。"""
    if wx is None:
        raise RuntimeError("wx 不可用")
    bundle = wx.BitmapBundle.FromSVGFile(svg_path, wx.Size(width, height))
    bitmap = bundle.GetBitmap(wx.Size(width, height))
    image = bitmap.ConvertToImage()
    if not image.IsOk():
        raise RuntimeError("SVG 光栅化失败: %s" % svg_path)
    return image


# ---------------------------------------------------------------- 校准

def _inject_markers(src_board, dst_board, board_bbox):
    """在板文件副本上注入两个校准标记(User.9 层),返回标记板坐标(nm)。

    标记放在板框对角附近(x、y 均不同),便于按 x 区分并求解完整仿射。
    坐标按源文件自身格式写入(mm 浮点 / nm 整数)。
    """
    x0, y0, x1, y1 = board_bbox
    if (x1 - x0) <= 0 or (y1 - y0) <= 0:
        x0, y0, x1, y1 = 0, 0, 10000000, 10000000
    inset = max(1000000, int(0.02 * (x1 - x0)))
    p1 = (x0 + inset, y0 + inset)
    p2 = (x1 - inset, y1 - inset)

    is_mm = _file_is_mm(src_board)
    fill_token = _fill_token(src_board)

    def fmt(v):
        return "%.6g" % (v / 1e6) if is_mm else str(int(v))

    radius = int(CALIB_MARKER_R)
    stroke = 150000
    template = ('(gr_circle (center %s %s) (end %s %s) '
                '(stroke (width %s) (type default)) (fill %s) '
                '(layer "%s") (uuid "ffffffff-ffff-ffff-ffff-ffffffffff%02x"))')
    marker1 = template % (fmt(p1[0]), fmt(p1[1]), fmt(p1[0] + radius),
                          fmt(p1[1]), fmt(stroke), fill_token, CALIB_LAYER, 1)
    marker2 = template % (fmt(p2[0]), fmt(p2[1]), fmt(p2[0] + radius),
                          fmt(p2[1]), fmt(stroke), fill_token, CALIB_LAYER, 2)
    with open(src_board, "r", encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.rstrip()
    idx = stripped.rfind(")")
    if idx < 0:
        raise RuntimeError("无法定位板文件结尾,校准失败")
    new_text = stripped[:idx] + "\n" + marker1 + "\n" + marker2 + "\n)\n"
    with open(dst_board, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    return [p1, p2]


def _marker_pixels(image, tol=_ALPHA_ON):
    """返回图像中有内容(alpha 大于阈值)的像素坐标列表。"""
    width = image.GetWidth()
    height = image.GetHeight()
    alpha = image.GetAlphaBuffer()
    pts = []
    step = 2
    for y in range(0, height, step):
        base = y * width
        for x in range(0, width, step):
            if alpha[base + x] > tol:
                pts.append((x, y))
    return pts


def calibrate(board_file, cli, board_bbox, tmp_dir, raster_size):
    """测量「板坐标(nm) → 图像像素」仿射,返回 (ax, cx, ay, cy)。

    像素 x = ax * 板x(nm) + cx;像素 y = ay * 板y(nm) + cy。
    通过注入两个已知板坐标的标记并定位其像素质心直接求解,
    与图像 y 轴方向、页面留白均无关。
    """
    tmp_board = os.path.join(tmp_dir,
                             "calib_" + os.path.basename(board_file))
    marker_pts = _inject_markers(board_file, tmp_board, board_bbox)
    out_svg = tmp_board + ".svg"
    export_layer_svg(tmp_board, CALIB_LAYER, out_svg, cli)
    if wx is None:
        return None
    image = rasterize_svg(out_svg, raster_size[0], raster_size[1])
    pts = _marker_pixels(image)
    if len(pts) < 4:
        return None

    def centroid(group):
        n = len(group) or 1
        return (sum(p[0] for p in group) / n, sum(p[1] for p in group) / n)

    pts.sort(key=lambda p: p[0])
    half = len(pts) // 2
    left, right = pts[:half], pts[half:]
    c_left, c_right = centroid(left), centroid(right)
    (bx1, by1), (bx2, by2) = marker_pts  # p1 在左,p2 在右

    def axis(px1, px2, b1, b2):
        denom = (b2 - b1)
        if abs(denom) < 1e-9:
            return 0.0, px1
        a = (px2 - px1) / denom
        return a, px1 - a * b1

    ax, cx = axis(c_left[0], c_right[0], bx1, bx2)
    ay, cy = axis(c_left[1], c_right[1], by1, by2)
    return (ax, cx, ay, cy)


# ---------------------------------------------------------------- 对齐与对比

def flatten(image, bg=(0, 0, 0)):
    """返回不透明副本:透明像素以 bg 填充,去掉 alpha 通道。"""
    if not image.HasAlpha():
        return image
    width = image.GetWidth()
    height = image.GetHeight()
    out = wx.Image(width, height)
    data = image.GetData()
    alpha = image.GetAlphaBuffer()
    buf = bytearray(data)
    for i in range(0, len(data), 3):
        if alpha[i // 3] <= 0:
            buf[i], buf[i + 1], buf[i + 2] = bg
    out.SetData(bytes(buf))
    return out


def align_images(img_a, img_b, aff_a, aff_b):
    """把 B 图按板坐标对齐到 A 图的像素空间,返回 (对齐后的 B 图, 叠加对比图)。"""
    wa = img_a.GetWidth()
    ha = img_a.GetHeight()
    scale_a = (abs(aff_a[0]) + abs(aff_a[2])) / 2.0
    scale_b = (abs(aff_b[0]) + abs(aff_b[2])) / 2.0
    ratio = scale_a / scale_b if scale_b else 1.0
    wb = max(1, int(round(img_b.GetWidth() * ratio)))
    hb = max(1, int(round(img_b.GetHeight() * ratio)))
    img_b_scaled = img_b.Scale(wb, hb, wx.IMAGE_QUALITY_HIGH)
    dx = int(round(aff_a[1] - aff_b[1] * ratio))
    dy = int(round(aff_a[3] - aff_b[3] * ratio))
    # 用 GraphicsContext 在黑色画布上按 alpha 合成 B 图
    canvas_bmp = wx.Bitmap(wa, ha, 32)
    dc = wx.MemoryDC(canvas_bmp)
    dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0)))
    dc.Clear()
    gc = wx.GraphicsContext.Create(dc)
    gc.DrawBitmap(wx.Bitmap(img_b_scaled), dx, dy, wb, hb)
    del gc
    dc.SelectObject(wx.NullBitmap)
    aligned = canvas_bmp.ConvertToImage()
    overlay = pixel_diff(img_a, aligned)
    return aligned, overlay


def _is_on(data, alpha, index, has_alpha, alpha_tol, bright_tol=80):
    if has_alpha:
        return alpha[index // 3] > alpha_tol
    return data[index] + data[index + 1] + data[index + 2] > bright_tol


def pixel_diff(img_a, img_b, alpha_tol=_ALPHA_ON, diff_tol=60):
    """像素级对比:红=删除(仅 A 有)、绿=新增(仅 B 有)、黄=修改、暗=未变。

    两图按像素空间对齐;有 alpha 通道时以 alpha 判定内容,否则以亮度判定。
    """
    wa = img_a.GetWidth()
    ha = img_a.GetHeight()
    data_a = img_a.GetData()
    data_b = img_b.GetData()
    has_a = img_a.HasAlpha()
    has_b = img_b.HasAlpha()
    alpha_a = img_a.GetAlphaBuffer() if has_a else None
    alpha_b = img_b.GetAlphaBuffer() if has_b else None
    out = wx.Image(wa, ha)
    data_o = bytearray(data_a)
    n = len(data_a)
    step = 3 if n <= 9_000_000 else 6  # 大图降采样提速
    for i in range(0, n - 2, step):
        a_on = _is_on(data_a, alpha_a, i, has_a, alpha_tol)
        b_on = _is_on(data_b, alpha_b, i, has_b, alpha_tol)
        if a_on and b_on:
            if (abs(data_a[i] - data_b[i]) + abs(data_a[i + 1] - data_b[i + 1])
                    + abs(data_a[i + 2] - data_b[i + 2]) > diff_tol):
                data_o[i], data_o[i + 1], data_o[i + 2] = 255, 200, 0
            else:
                data_o[i] = data_a[i] // 3
                data_o[i + 1] = data_a[i + 1] // 3
                data_o[i + 2] = data_a[i + 2] // 3
        elif a_on:
            data_o[i], data_o[i + 1], data_o[i + 2] = 255, 60, 60
        elif b_on:
            data_o[i], data_o[i + 1], data_o[i + 2] = 60, 220, 80
        else:
            data_o[i] = data_o[i + 1] = data_o[i + 2] = 0
    out.SetData(bytes(data_o))
    return out


# ---------------------------------------------------------------- 渲染与异步

def render_pair(paths, layer, board_bbox, cli, tmp_dir, width=1600):
    """渲染两版快照的指定图层,返回结果字典。paths = (旧版, 新版)。"""
    bw = max(1, board_bbox[2] - board_bbox[0])
    bh = max(1, board_bbox[3] - board_bbox[1])
    height = max(100, int(round(width * bh / bw)))
    raster_size = (width, height)
    safe = _safe(layer)
    svg_a = os.path.join(tmp_dir, "layer_a_%s.svg" % safe)
    svg_b = os.path.join(tmp_dir, "layer_b_%s.svg" % safe)
    export_layer_svg(paths[0], layer, svg_a, cli)
    export_layer_svg(paths[1], layer, svg_b, cli)
    if wx is None:
        raise RuntimeError("wx 不可用,无法处理图像")
    img_a = rasterize_svg(svg_a, width, height)
    img_b = rasterize_svg(svg_b, width, height)
    aff_a = calibrate(paths[0], cli, board_bbox, tmp_dir, raster_size)
    aff_b = calibrate(paths[1], cli, board_bbox, tmp_dir, raster_size)
    if aff_a is None or aff_b is None:
        raise RuntimeError("校准失败:无法定位校准标记")
    aligned, overlay = align_images(img_a, img_b, aff_a, aff_b)
    return {"layer": layer, "img_a": flatten(img_a), "img_b": flatten(img_b),
            "aligned": flatten(aligned), "overlay": overlay, "aff": aff_a}


def render_pair_async(paths, layer, board_bbox, cli, tmp_dir, width,
                      on_done, on_error=None):
    """后台线程渲染,完成后通过 wx.CallAfter 回调。"""
    def worker():
        try:
            result = render_pair(paths, layer, board_bbox, cli, tmp_dir, width)
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                if wx is not None:
                    wx.CallAfter(on_error, str(exc))
                else:
                    on_error(str(exc))
            return
        if wx is not None:
            wx.CallAfter(on_done, result)
        else:
            on_done(result)

    threading.Thread(target=worker, daemon=True).start()


def _safe(layer):
    return layer.replace(".", "_")
