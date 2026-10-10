# -*- mode: python ; coding: utf-8 -*-
# 流光 LIUG 桌面版打包配置（整个应用：托盘 + 主界面 + 桌面小组件）
#   python -m PyInstaller --noconfirm liug.spec
# 产物：dist/liug.exe（单文件、无控制台窗口）
#
# 结构口径（与源码目录一致）：
#   - 入口 desktop/main.py（桌面壳：托盘/窗口/内嵌服务）
#   - 业务核心 core/（与远程后端共享）；本地免登录认证 desktop/local_auth.py（单机模式）
#   - 用户管理逻辑（server/users.py 账户体系）不进入 exe：desktop 侧不 import 它，
#     并在 excludes 里显式排除作为兜底
from PyInstaller.utils.hooks import collect_all
import os
import sys
from pathlib import Path

datas = [
    ('client/dist', 'client/dist'),
]
binaries = []
# conda Python 的运行时依赖 DLL 在 Library/bin，PyInstaller 不会自动打包（否则 _ssl/_ctypes/_sqlite3 等导入失败）
for dll in ('libcrypto-3-x64.dll', 'libssl-3-x64.dll',
            'ffi.dll', 'ffi-7.dll', 'ffi-8.dll',
            'sqlite3.dll', 'liblzma.dll', 'libbz2.dll', 'zlib.dll', 'libexpat.dll'):
    p = Path(sys.base_prefix) / 'Library' / 'bin' / dll
    if p.exists():
        binaries.append((str(p), '.'))

hiddenimports = [
    # uvicorn 通过字符串动态导入的模块，静态分析抓不到
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # pystray 按平台动态导入的后端
    'pystray._win32',
]
# pywebview（Windows 后端 pythonnet/clr_loader）与 pystray：数据文件、DLL、子模块全收集
for pkg in ('webview', 'pythonnet', 'clr_loader', 'pystray'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['desktop/main.py'],
    pathex=[SPECPATH, os.path.join(SPECPATH, 'desktop')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 用户管理（server/users.py 账户体系 + server/routes_admin.py 管理端）不打包进 exe：
    # desktop 不引用它们，此处显式排除兜底
    excludes=['users', 'routes_api', 'routes_system', 'routes_admin'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='liug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='desktop/assets/liug.ico',
)
