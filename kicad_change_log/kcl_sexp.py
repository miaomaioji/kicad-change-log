# -*- coding: utf-8 -*-
"""KiCad s-expression 解析器(纯标准库,不依赖 wx / pcbnew)。"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)


def tokenize(text):
    """把 s-expression 文本切成 token 列表。

    处理括号、带引号字符串(含 \\" \\\\ \\n 转义)与普通原子。
    """
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "(":
            tokens.append("(")
            i += 1
            continue
        if c == ")":
            tokens.append(")")
            i += 1
            continue
        if c == '"':
            i += 1
            buf = []
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    if nxt == "n":
                        buf.append("\n")
                    else:
                        buf.append(nxt)
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.append(ch)
                i += 1
            tokens.append("".join(buf))
            continue
        start = i
        while i < n and text[i] not in " \t\r\n()":
            i += 1
        tokens.append(text[start:i])
    return tokens


def parse(text):
    """解析 s-expression 文本,返回嵌套列表(字符串为原子)。"""
    tokens = tokenize(text)
    pos = 0

    def parse_expr():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst = []
            while tokens[pos] != ")":
                lst.append(parse_expr())
            pos += 1
            return lst
        return tok

    out = []
    while pos < len(tokens):
        out.append(parse_expr())
    return out


def find(node, key):
    """返回 node 下第一个头为 key 的子列表,找不到返回 None。"""
    if not isinstance(node, list):
        return None
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == key:
            return child
    return None


def find_all(node, key):
    """返回 node 下所有头为 key 的子列表。"""
    out = []
    if not isinstance(node, list):
        return out
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == key:
            out.append(child)
    return out


def attr(node, key, index=1, default=None):
    """读取 (key v1 v2 ...) 中第 index 个值。"""
    child = find(node, key)
    if child is not None and len(child) > index:
        return child[index]
    return default


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
