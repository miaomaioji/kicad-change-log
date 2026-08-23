# -*- coding: utf-8 -*-
"""打包为 KiCad PCM(Package and Content Manager)兼容 zip。

用法:
    python build_pcm.py
"""

import json
import os
import zipfile

PKG_NAME = "kicad_change_log"
GITHUB_REPO = "miaomaioji/kicad-change-log"
# 版本号:默认 1.1.0,可由环境变量 KCL_VERSION 覆盖(CI 中用 tag 注入)
VERSION = (os.environ.get("KCL_VERSION") or "1.1.0").lstrip("v")

METADATA = {
    "$schema": "https://go.kicad.org/pcm/schemas/v1",
    "name": "项目操作日志与变更可视化",
    "identifier": "com.github.kicad-change-log",
    "description": "记录 PCB 项目快照,以变动日志与图层对比图可视化每次改动",
    "description_full": (
        "两个独立窗口:\n"
        "1) 变动日志窗口:按位号记录变更明细,如「X1 坐标变更 (11, 23) → "
        "(111, 2222)」,支持新增/删除/修改的属性级对比;\n"
        "2) 变更可视化窗口:参照 DRC 与嘉立创 DFM 风格,左侧按图层分组的变动"
        "列表,右侧 kicad-cli 渲染的图层对比图(并排/红绿叠加/滑块分割),"
        "点击条目联动定位到板子画布。\n\n"
        "板文件保存后自动生成本地快照(无需 Git),也可手动记录。"
    ),
    "type": "plugin",
    "author": {
        "name": "kicad-change-log contributors",
        "contact": {
            "web": "https://github.com/%s" % GITHUB_REPO,
        },
    },
    "license": "MIT",
    "resources": {
        "homepage": "https://github.com/%s" % GITHUB_REPO,
    },
    "tags": ["pcb", "diff", "log"],
    "versions": [
        {
            "version": VERSION,
            "status": "stable",
            "kicad_version": "8.0",
            "download_url": (
                "https://github.com/%s/releases/download/v%s/"
                "kicad_change_log_v%s.zip" % (GITHUB_REPO, VERSION, VERSION)
            ),
        }
    ],
}


def _validate(meta):
    """按 PCM v1 schema 关键必填项做最小校验(与官方 pcm.v1.schema.json 一致)。"""
    required = ["name", "description", "description_full", "identifier",
                "type", "author", "license", "resources", "versions"]
    for key in required:
        assert key in meta, "缺少必填字段: %s" % key
    assert "name" in meta["author"] and "contact" in meta["author"], \
        "author 需要 name 与 contact"
    for version in meta["versions"]:
        for key in ("version", "status", "kicad_version"):
            assert key in version, "版本缺少字段: %s" % key
    print("元数据校验通过(PCM v1 必填项)")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    _validate(METADATA)
    dist = os.path.join(here, "dist")
    os.makedirs(dist, exist_ok=True)
    zip_path = os.path.join(dist, "kicad_change_log_v%s.zip" % VERSION)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json",
                    json.dumps(METADATA, ensure_ascii=False, indent=2))
        src_root = os.path.join(here, PKG_NAME)
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, here).replace("\\", "/")
                zf.write(full, "plugins/" + rel)
    print("已生成:", zip_path)
    print("提示:metadata.json 的 download_url 指向 GitHub Releases;"
          "发布 v%s tag 并上传 zip 后即可用于 PCM 仓库。" % VERSION)


if __name__ == "__main__":
    main()
