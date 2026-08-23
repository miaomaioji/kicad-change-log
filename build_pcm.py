# -*- coding: utf-8 -*-
"""打包为 KiCad PCM(Package and Content Manager)兼容 zip。

包结构遵循官方文档(https://dev-docs.kicad.org/zh-cn/addons/):

    Archive root
    |- plugins        // 插件文件平铺放置(不得有二级子目录)
    |   |- kcl_plugin.py
    |   |- ...
    |   |- icon_24.png    // 24x24 工具栏图标
    |- resources
    |   |- icon.png       // 64x64 PCM 图标
    |- metadata.json      // 元数据(不含 download_* 字段)

同时生成 `dist/metadata.json`:供提交 KiCad 官方元数据仓库
(https://gitlab.com/kicad/addons/metadata,目录
packages/com.github.miaomaioji.kicad-change-log/)使用,
含 download_url / download_sha256 / download_size / install_size。

用法:
    python build_pcm.py
"""

import hashlib
import json
import os
import zipfile

PKG_NAME = "kicad_change_log"
GITHUB_REPO = "miaomaioji/kicad-change-log"
IDENTIFIER = "com.github.%s" % GITHUB_REPO.replace("/", ".")
# 版本号:默认 1.1.0,可由环境变量 KCL_VERSION 覆盖(CI 中用 tag 注入)
VERSION = (os.environ.get("KCL_VERSION") or "1.1.0").lstrip("v")

ZIP_NAME = "kicad_change_log_v%s.zip" % VERSION
DOWNLOAD_URL = ("https://github.com/%s/releases/download/v%s/%s"
                % (GITHUB_REPO, VERSION, ZIP_NAME))

# zip 包内的 metadata.json(官方要求 download_* 键只能出现在
# 元数据仓库提交版中,不能放在 zip 内的 metadata.json 里)
METADATA = {
    "$schema": "https://go.kicad.org/pcm/schemas/v1",
    "name": "Change Log and Layer Diff",
    "identifier": IDENTIFIER,
    "description": (
        "Snapshot-based change log and layer diff visualization "
        "for PCB projects."
    ),
    "description_full": (
        "Two windows inside the KiCad PCB editor:\n"
        "1) Change log window: per-reference change details such as "
        "'X1 position (11, 23) -> (111, 2222)', with added/removed/"
        "modified attribute-level diffs, color coding and type filters.\n"
        "2) Visualization window (DRC / JLC DFM style): changes grouped "
        "by layer on the left; kicad-cli rendered layer comparison on "
        "the right (side-by-side / red-green overlay / slider), with "
        "click-to-locate on the real canvas.\n\n"
        "Snapshots are created automatically after saving the board "
        "(no Git required); manual snapshots are also supported."
    ),
    "type": "plugin",
    "author": {
        "name": "kicad-change-log contributors",
        "contact": {"web": "https://github.com/%s" % GITHUB_REPO},
    },
    "maintainer": {
        "name": "kicad-change-log contributors",
        "contact": {"web": "https://github.com/%s" % GITHUB_REPO},
    },
    "license": "MIT",
    "resources": {"homepage": "https://github.com/%s" % GITHUB_REPO},
    "tags": ["pcb", "diff", "log"],
    "versions": [
        {
            "version": VERSION,
            "status": "stable",
            "kicad_version": "8.0",
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


def _package_entries(src_root):
    """返回 [(源文件绝对路径, zip 内路径)]。

    官方要求:插件文件直接平铺在 plugins/ 子目录中(无二级子目录),
    与插件无关的额外文件不得打包。
    """
    entries = []
    for name in sorted(os.listdir(src_root)):
        full = os.path.join(src_root, name)
        if not os.path.isfile(full):
            continue
        if name == "icon.png":
            entries.append((full, "resources/icon.png"))
        elif name == "icon_24.png":
            entries.append((full, "plugins/icon_24.png"))
        elif name == "kcl_settings.json":
            entries.append((full, "plugins/kcl_settings.json"))
        elif name.endswith(".py") and name != "__init__.py":
            entries.append((full, "plugins/" + name))
    return entries


def _write_zip(zip_path, entries):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json",
                    json.dumps(METADATA, ensure_ascii=False, indent=2))
        for full, arc in entries:
            zf.write(full, arc)


def _repo_metadata(zip_path, install_size):
    """生成提交给官方元数据仓库的 metadata.json(含 download_* 字段)。"""
    size = os.path.getsize(zip_path)
    with open(zip_path, "rb") as fh:
        sha256 = hashlib.sha256(fh.read()).hexdigest()
    meta = json.loads(json.dumps(METADATA))
    meta["versions"][0].update({
        "download_url": DOWNLOAD_URL,
        "download_sha256": sha256,
        "download_size": size,
        "install_size": install_size,
    })
    return meta


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    _validate(METADATA)
    src_root = os.path.join(here, PKG_NAME)
    assert os.path.isdir(src_root), "未找到插件源码目录: %s" % src_root
    dist = os.path.join(here, "dist")
    os.makedirs(dist, exist_ok=True)

    entries = _package_entries(src_root)
    assert entries, "没有可打包的插件文件"
    zip_path = os.path.join(dist, ZIP_NAME)
    _write_zip(zip_path, entries)

    install_size = sum(os.path.getsize(f) for f, _ in entries)
    install_size += len(
        json.dumps(METADATA, ensure_ascii=False).encode("utf-8"))
    repo_meta = _repo_metadata(zip_path, install_size)
    repo_path = os.path.join(dist, "metadata.json")
    with open(repo_path, "w", encoding="utf-8") as fh:
        json.dump(repo_meta, fh, ensure_ascii=False, indent=2)

    print("已生成:", zip_path)
    print("已生成:", repo_path, "(提交 KiCad 官方元数据仓库用)")
    print("download_sha256:", repo_meta["versions"][0]["download_sha256"])
    print("发布 v%s tag 后下载地址生效: %s" % (VERSION, DOWNLOAD_URL))
    print("官方仓库提交:将 dist/metadata.json 提交到")
    print("  https://gitlab.com/kicad/addons/metadata 的")
    print("  packages/%s/ 目录。" % IDENTIFIER)


if __name__ == "__main__":
    main()
