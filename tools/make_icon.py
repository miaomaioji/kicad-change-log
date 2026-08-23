# -*- coding: utf-8 -*-
"""生成插件图标 icon.png(纯标准库 PNG 编码,无需 PIL)。

用法:
    python tools/make_icon.py
"""

import os
import struct
import zlib

SIZE = 64


def inside_round_rect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = max(x0 + r, min(x, x1 - r))
    cy = max(y0 + r, min(y, y1 - r))
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def build_rows():
    rows = []
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            x, y = px + 0.5, py + 0.5
            col = (0, 0, 0, 0)  # 透明
            if inside_round_rect(x, y, 2, 2, 61, 61, 14):
                col = (42, 90, 223, 255)  # 蓝色圆角底
            # 白色页面
            if 12 <= x <= 38 and 14 <= y <= 50:
                col = (255, 255, 255, 255)
            # 页角折痕
            if 32 <= x <= 38 and 14 <= y <= 20:
                col = (200, 214, 245, 255)
            # 页面上的行
            if 16 <= x <= 30 and abs(y - 24) <= 1:
                col = (122, 139, 184, 255)
            if 16 <= x <= 30 and abs(y - 31) <= 1:
                col = (122, 139, 184, 255)
            if 16 <= x <= 25 and abs(y - 38) <= 1:
                col = (122, 139, 184, 255)
            # 绿圈(新增)/ 红圈(删除) + 白色描边
            g = (x - 45) ** 2 + (y - 36) ** 2
            r = (x - 54) ** 2 + (y - 45) ** 2
            if g <= 25:
                col = (46, 204, 113, 255)
            if r <= 25:
                col = (231, 76, 60, 255)
            if 49 <= g <= 64:
                col = (255, 255, 255, 255)
            if 49 <= r <= 64:
                col = (255, 255, 255, 255)
            row += bytes(col)
        rows.append(bytes(row))
    return rows


def png_bytes(width, height, rgba_rows):
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    raw = b"".join(b"\x00" + row for row in rgba_rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "kicad_change_log", "icon.png")
    with open(out_path, "wb") as fh:
        fh.write(png_bytes(SIZE, SIZE, build_rows()))
    print("已生成:", os.path.abspath(out_path))


if __name__ == "__main__":
    main()
