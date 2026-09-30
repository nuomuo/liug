"""桌面四象限小组件启动器（pywebview 无边框透明置顶窗口）

优先复用本机已在运行的主服务（http://localhost:4300），避免双进程同时写 SQLite；
主服务未运行时在当前进程内嵌一份 uvicorn（127.0.0.1 随机端口）独立工作。

启动：python server/desktop_widget.py
测试库：$env:DIDA_USERS_DB_PATH='data/users.test.db'; $env:DIDA_USERS_DIR='data/users-test'; python server/desktop_widget.py
"""
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

# PyInstaller 冻结模式（quadrant.exe）：
# - 数据目录默认放在 exe 同级 data/ 下（可用 DIDA_USERS_DB_PATH / DIDA_USERS_DIR 覆盖）
# - 静态资源指向 _MEIPASS 解包目录内打包的 client/dist 副本
if getattr(sys, 'frozen', False):
    _EXE_DIR = Path(sys.executable).resolve().parent
    _MEIPASS = Path(sys._MEIPASS)
    os.environ.setdefault('DIDA_USERS_DB_PATH', str(_EXE_DIR / 'data' / 'users.db'))
    os.environ.setdefault('DIDA_USERS_DIR', str(_EXE_DIR / 'data' / 'users'))
    os.environ.setdefault('DIDA_DIST_DIR', str(_MEIPASS / 'client' / 'dist'))
else:
    _EXE_DIR = None

import users

BASE_DIR = Path(__file__).resolve().parent
MAIN_SERVER = 'http://localhost:4300'


def _main_server_alive() -> bool:
    """主服务探活：/api/auth/me 返回 200/401 即视为本应用已在运行（401 = 未登录但服务正常）"""
    try:
        import httpx
        r = httpx.get(MAIN_SERVER + '/api/auth/me', timeout=0.8)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_embedded_server() -> int:
    """进程内嵌 uvicorn（随机端口），复用 app.py 的同一份 FastAPI 应用与数据库配置"""
    from app import app  # 延迟导入：仅独立运行时加载
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
    threading.Thread(target=server.run, daemon=True).start()
    return port


class _WidgetApi:
    """暴露给前端的窗口控制（前端通过 window.pywebview.api.* 调用）"""

    def __init__(self):
        self._window = None

    def close(self):
        if self._window:
            self._window.destroy()

    def minimize(self):
        if self._window:
            self._window.minimize()


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit('缺少依赖 pywebview，请先执行：pip install pywebview')

    # 显式指定服务地址（测试/远程场景）；否则优先复用本机主服务，最后内嵌独立运行
    # DIDA_WIDGET_FORCE_EMBEDDED=1 可跳过探活强制内嵌（打包验证/数据隔离场景）
    override = os.environ.get('DIDA_WIDGET_SERVER_URL', '').rstrip('/')
    if override:
        base_url = override
        print(f'[widget] 使用指定服务 {base_url}')
    elif not os.environ.get('DIDA_WIDGET_FORCE_EMBEDDED') and _main_server_alive():
        base_url = MAIN_SERVER
        print(f'[widget] 复用已运行的主服务 {MAIN_SERVER}')
    else:
        # 独立运行：初始化用户主库（对齐 app.py 启动流程）后内嵌起服务
        # 冻结模式下旧单用户库迁移源取 exe 同级 data/schedule.db
        legacy = (_EXE_DIR if _EXE_DIR else BASE_DIR.parent) / 'data' / 'schedule.db'
        users.bootstrap_users(legacy_db_path=legacy)
        port = _start_embedded_server()
        base_url = f'http://127.0.0.1:{port}'
        print(f'[widget] 内嵌服务已启动 {base_url}')

    api = _WidgetApi()
    window = webview.create_window(
        '四象限',
        f'{base_url}/quadrant',
        width=560,
        height=440,
        min_size=(420, 320),
        frameless=True,   # 无边框：UI 完全由前端面板绘制
        transparent=True,  # 透明背景：只显示小组件面板本体
        on_top=True,      # 窗口置顶，常驻桌面
        easy_drag=True,   # 按住页面空白处（如标题栏）即可拖动窗口
        js_api=api,
    )
    api._window = window
    webview.start()


if __name__ == '__main__':
    main()
