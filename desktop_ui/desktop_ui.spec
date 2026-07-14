# -*- mode: python ; coding: utf-8 -*-
import json
import os
import sys


with open("version.json", encoding="utf-8") as file:
    version_data = json.load(file)

name = f"{version_data['name']}-Desktop-v{version_data['version']}"
config_files = [
    "config.ini",
    "demo.txt",
    "local.txt",
    "whitelist.txt",
    "blacklist.txt",
    "subscribe.txt",
    "epg.txt",
    "alias.txt",
]
datas = [(os.path.join("config", item), "config") for item in config_files]
datas.extend([
    ("config/logo", "config/logo"),
    ("locales", "locales"),
    ("utils/ip_checker/data/qqwry.ipdb", "utils/ip_checker/data"),
    ("favicon.ico", "."),
    ("version.json", "."),
    ("service/nginx.conf.template", "service"),
])
if sys.platform == "win32":
    datas.append(("utils/nginx-rtmp-win32", "utils/nginx-rtmp-win32"))

a = Analysis(
    ["desktop_ui/app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="favicon.ico" if sys.platform == "win32" else None,
)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=name,
)
if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name=f"{name}.app",
        icon="favicon.ico",
        bundle_identifier="com.iptv-api.desktop",
        info_plist={"NSHighResolutionCapable": True},
    )
