"""桌面四象限小组件启动器（pywebview 无边框透明置顶窗口）

优先复用本机已在运行的主服务（http://localhost:4300），避免双进程同时写 SQLite；
主服务未运行时在当前进程内嵌一份 uvicorn（127.0.0.1 随机端口）独立工作。

启动：python server/desktop_widget.py
测试库：$env:LIUG_USERS_DB_PATH='data/users.test.db'; $env:LIUG_USERS_DIR='data/users-test'; python server/desktop_widget.py
"""
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

# PyInstaller 冻结模式（quadrant.exe）：
# - 数据目录默认放在 exe 同级 data/ 下（可用 LIUG_USERS_DB_PATH / LIUG_USERS_DIR 覆盖）
# - 静态资源指向 _MEIPASS 解包目录内打包的 client/dist 副本
if getattr(sys, 'frozen', False):
    _EXE_DIR = Path(sys.executable).resolve().parent
    _MEIPASS = Path(sys._MEIPASS)
    os.environ.setdefault('LIUG_USERS_DB_PATH', str(_EXE_DIR / 'data' / 'users.db'))
    os.environ.setdefault('LIUG_USERS_DIR', str(_EXE_DIR / 'data' / 'users'))
    os.environ.setdefault('LIUG_DIST_DIR', str(_MEIPASS / 'client' / 'dist'))
else:
    _EXE_DIR = None

import users
from widget_window import MoveSession, ResizeSession

BASE_DIR = Path(__file__).resolve().parent
MAIN_SERVER = 'http://localhost:4300'

# 与 desktop_app.py 保持同口径：窗口标题（Win32 定位用）与尺寸上下限
WIDGET_TITLE = '四象限'
WIDGET_MIN_SIZE = (420, 320)
WIDGET_MAX_SIZE = (1100, 900)


def _dist_version() -> str:
    """取 client/dist/index.html 的 mtime 作版本号，附加到 URL 破 WebView2 持久缓存（同 desktop_app.py）"""
    try:
        dist = Path(os.environ.get('LIUG_DIST_DIR') or (BASE_DIR.parent / 'client' / 'dist'))
        return str(int((dist / 'index.html').stat().st_mtime))
    except OSError:
        return '0'


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
        self._resize = None  # 进行中的拖拽缩放会话（widget_window.ResizeSession）
        self._move = None    # 进行中的窗口拖动会话（widget_window.MoveSession）

    def close(self):
        if self._window:
            self._window.destroy()

    def minimize(self):
        if self._window:
            self._window.minimize()

    # ---- 标题栏拖动窗口（HTCAPTION 原生拖动在 WebView2 下不生效，改用与缩放同款的指针方案）----

    def begin_move(self):
        """开始拖动窗口：标题栏 pointerdown 时调用"""
        s = MoveSession(WIDGET_TITLE)
        self._move = s if s.begin() else None

    def update_move(self):
        """拖动中按光标增量平移窗口（每次 pointermove 调一次）"""
        if self._move:
            self._move.update()

    def end_move(self):
        """结束拖动（独立小组件不做几何持久化）"""
        if self._move:
            self._move.end()
            self._move = None

    def resize(self, dw=0, dh=0, w=None, h=None):
        """调整窗口尺寸（像素）：传 w/h 直接设置，传 dw/dh 按当前尺寸增量调整，夹在上下限内"""
        if not self._window:
            return None
        if w is None or h is None:
            w, h = self._window.width + int(dw), self._window.height + int(dh)
        w = max(WIDGET_MIN_SIZE[0], min(WIDGET_MAX_SIZE[0], int(w)))
        h = max(WIDGET_MIN_SIZE[1], min(WIDGET_MAX_SIZE[1], int(h)))
        self._window.resize(w, h)
        return [w, h]

    # ---- 拖拽边缘/角落缩放（frameless 窗口原生不支持，用 Win32 补齐，见 widget_window.py）----

    def begin_resize(self, edge):
        """开始一次拖拽缩放：edge 为 n/s/e/w/ne/nw/se/sw"""
        s = ResizeSession(WIDGET_TITLE, WIDGET_MIN_SIZE, WIDGET_MAX_SIZE)
        self._resize = s if s.begin(edge) else None

    def update_resize(self):
        """拖动过程中按光标增量移动+缩放窗口（每次 pointermove 调一次）"""
        if self._resize:
            self._resize.update()

    def end_resize(self):
        """结束拖拽（独立小组件不做几何持久化）"""
        if self._resize:
            self._resize.end()
            self._resize = None


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit('缺少依赖 pywebview，请先执行：pip install pywebview')

    # 显式指定服务地址（测试/远程场景）；否则优先复用本机主服务，最后内嵌独立运行
    # LIUG_WIDGET_FORCE_EMBEDDED=1 可跳过探活强制内嵌（打包验证/数据隔离场景）
    override = os.environ.get('LIUG_WIDGET_SERVER_URL', '').rstrip('/')
    if override:
        base_url = override
        print(f'[widget] 使用指定服务 {base_url}')
    elif not os.environ.get('LIUG_WIDGET_FORCE_EMBEDDED') and _main_server_alive():
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
        WIDGET_TITLE, f'{base_url}/quadrant?v={_dist_version()}',
        width=560,
        height=440,
        min_size=(420, 320),
        frameless=True,   # 无边框：UI 完全由前端面板绘制
        transparent=True,  # 透明背景：只显示小组件面板本体
        on_top=True,      # 窗口置顶，常驻桌面
        easy_drag=False,  # 必须显式关闭（默认 True！）：其监听任意 mousedown，会与页面内
        # 拖任务/缩放手柄冲突（HTML5 拖拽吞掉 mouseup 后窗口跟着鼠标跑）；拖动改由标题栏 begin/update/end_move API 实现
        js_api=api,
    )
    api._window = window

    def _on_restored():
        # WebView2 透明窗口最小化再还原后透明合成会失效（面板背后露出窗体底色），
        # hide→show 一次强制重建合成层即可恢复（pywebview 初始化时亦用同类 hack）
        time.sleep(0.2)  # 等还原动画结束、窗口状态稳定
        try:
            window.hide()
            time.sleep(0.3)
            window.show()
        except Exception:
            pass

    window.events.restored += _on_restored
    webview.start()


if __name__ == '__main__':
    main()
