"""桌面四象限小组件独立启动器（pywebview 无边框透明置顶窗口）

优先复用本机已在运行的主服务（按 data/service-port.json 发现其粘性端口，兜底 4300），
避免双进程同时写 SQLite；主服务未运行时在当前进程内嵌一份 uvicorn（127.0.0.1 随机端口）
独立工作。独立运行时使用本地免登录认证（desktop/local_auth.py 单机模式），不含用户管理逻辑，
也不启动云端同步引擎（同步由主服务进程负责）。

启动：python desktop/desktop_widget.py
测试：$env:LIUG_DATA_DIR='<临时目录>'; $env:LIUG_USERS_DIR='<临时目录>/users'; python desktop/desktop_widget.py
"""
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

# PyInstaller 冻结模式：
# - 数据目录默认放在 exe 同级 data/ 下（可用 LIUG_DATA_DIR / LIUG_USERS_DIR 覆盖）
# - 静态资源指向 _MEIPASS 解包目录内打包的 client/dist 副本
if getattr(sys, 'frozen', False):
    _EXE_DIR = Path(sys.executable).resolve().parent
    _MEIPASS = Path(sys._MEIPASS)
    os.environ.setdefault('LIUG_DATA_DIR', str(_EXE_DIR / 'data'))
    os.environ.setdefault('LIUG_USERS_DIR', str(_EXE_DIR / 'data' / 'users'))
    os.environ.setdefault('LIUG_DIST_DIR', str(_MEIPASS / 'client' / 'dist'))
else:
    _EXE_DIR = None

# 开发模式：让 desktop/ 内模块能找到根目录的 core 包（冻结模式由 PyInstaller pathex 处理）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from widget_window import MoveSession, ResizeSession  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
MAIN_SERVER = 'http://localhost:4300'

# 与 desktop/main.py 保持同口径：窗口标题（Win32 定位用）与尺寸上下限
WIDGET_TITLE = '四象限'
WIDGET_MIN_SIZE = (420, 320)
WIDGET_MAX_SIZE = (1100, 900)
# 透明合成掉线时露出的窗口兜底底色（pywebview 透明窗口默认纯白，掉线时会闪出刺眼白板）
WIDGET_FALLBACK_BG = '#181a20'

# 透明合成重建（hide→show）的节流：最小间隔 + 互斥锁，防止自激循环（同 desktop/main.py）
_REASSERT_LOCK = threading.Lock()
_REASSERT_COOLDOWN = 0.8  # 秒
_reassert_last = {'t': 0.0}


def _reassert_widget_transparency(win, delay=0.0):
    """强制重建透明窗口的合成层（hide→show），恢复半透明面板外观。

    WebView2 透明窗口的合成层会在启动瞬间、最小化→还原、切出切回前台、DWM 重排等时机掉线，
    此时窗口露出兜底底色（WIDGET_FALLBACK_BG）。hide→show 一次让 DWM 重建合成层即可恢复。
    同一窗口在冷却期内只执行一次，避免自激（同 desktop/main.py）。
    """
    if win is None:
        return
    now = time.monotonic()
    if now - _reassert_last['t'] < _REASSERT_COOLDOWN:
        return
    _reassert_last['t'] = now

    def _run():
        if delay > 0:
            time.sleep(delay)
        with _REASSERT_LOCK:
            try:
                win.hide()
                time.sleep(0.25)
                win.show()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name='widget-reassert').start()


def _set_widget_fallback_bg(win) -> None:
    """把透明窗口的原生 Form 底色改成暗色（同 desktop/main.py）。

    transparent=True 时 pywebview 会忽略 background_color（见 desktop/main.py 注释），
    Form 底色会保持 WinForms 默认浅色，合成层未就绪时露出「白色背板」；
    这里直接改原生 Form 的 BackColor。
    """
    if sys.platform != 'win32' or win is None:
        return
    try:
        form = getattr(win, 'native', None)
        if form is None:
            return
        from System import Func, Type
        from System.Drawing import Color

        def _apply():
            try:
                form.BackColor = Color.FromArgb(0x18, 0x1A, 0x20)
            except Exception:
                pass

        if form.InvokeRequired:  # 非 GUI 线程时切回 GUI 线程执行
            form.Invoke(Func[Type](_apply))
        else:
            _apply()
    except Exception:
        pass


def _data_dir() -> Path:
    env = os.environ.get('LIUG_DATA_DIR')
    if env:
        return Path(env)
    return (_EXE_DIR if _EXE_DIR else BASE_DIR.parent) / 'data'


def _dist_version() -> str:
    """取 client/dist/index.html 的 mtime 作版本号，附加到 URL 破 WebView2 持久缓存（同 desktop/main.py）"""
    try:
        dist = Path(os.environ.get('LIUG_DIST_DIR') or (BASE_DIR.parent / 'client' / 'dist'))
        return str(int((dist / 'index.html').stat().st_mtime))
    except OSError:
        return '0'


def _main_server_candidates():
    """主服务候选地址：粘性端口文件（动态端口的主服务）在前，4300 兜底（老版本/默认）"""
    urls = []
    try:
        d = json.loads((_data_dir() / 'service-port.json').read_text(encoding='utf-8'))
        p = int(d['port'])
        if 1024 <= p <= 65535:
            urls.append(f'http://127.0.0.1:{p}')
    except Exception:
        pass
    urls.append(MAIN_SERVER)
    return urls


def _server_alive(base_url: str) -> bool:
    """主服务探活：/api/auth/me 返回 200/401 即视为本应用已在运行（401 = 未登录但服务正常）"""
    try:
        import httpx
        r = httpx.get(base_url + '/api/auth/me', timeout=0.8)
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
    """进程内嵌 uvicorn（随机端口）：core 业务核心 + 本地单用户认证（不含用户管理）"""
    from core.app_factory import create_app
    from local_auth import ensure_local_secret, get_user_id, router as auth_router
    ensure_local_secret()
    app = create_app(get_user_id, auth_router)
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

    def reassert_transparency(self):
        """窗口重新聚焦时调用：切出/切回前台后透明合成可能掉线，重建一次合成层"""
        _reassert_widget_transparency(self._window)

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
        """结束拖动（独立小组件不做几何持久化）"""
        if self._resize:
            self._resize.end()
            self._resize = None


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit('缺少依赖 pywebview，请先执行：python -m pip install -r desktop/requirements.txt')

    # 显式指定服务地址（测试/远程场景）；否则优先复用本机主服务（粘性端口文件 → 4300 兜底），
    # 最后内嵌独立运行；LIUG_WIDGET_FORCE_EMBEDDED=1 可跳过探活强制内嵌（打包验证/数据隔离场景）
    override = os.environ.get('LIUG_WIDGET_SERVER_URL', '').rstrip('/')
    if override:
        base_url = override
        print(f'[widget] 使用指定服务 {base_url}')
    elif not os.environ.get('LIUG_WIDGET_FORCE_EMBEDDED'):
        found = next((u for u in _main_server_candidates() if _server_alive(u)), '')
        if found:
            base_url = found
            print(f'[widget] 复用已运行的主服务 {base_url}')
        else:
            port = _start_embedded_server()
            base_url = f'http://127.0.0.1:{port}'
            print(f'[widget] 内嵌服务已启动 {base_url}')
    else:
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
        background_color=WIDGET_FALLBACK_BG,  # 兜底底色：透明合成掉线时露出暗色而非默认纯白
        on_top=True,      # 窗口置顶，常驻桌面
        easy_drag=False,  # 必须显式关闭（默认 True！）：其监听任意 mousedown，会与页面内
        # 拖任务/缩放手柄冲突（HTML5 拖拽吞掉 mouseup 后窗口跟着鼠标跑）；拖动改由标题栏 begin/update/end_move API 实现
        js_api=api,
    )
    api._window = window

    def _on_shown():
        # 兜底底色在这里改：transparent 窗口下 background_color 被 pywebview 忽略
        _set_widget_fallback_bg(window)

    def _on_restored():
        # 最小化→还原后透明合成常掉线（面板背后露出兜底底色），重建一次合成层恢复
        _reassert_widget_transparency(window, delay=0.2)

    def _on_loaded():
        # 首帧绘制完成后再重建合成层：shown 早于导航开始（pywebview 的 Show/Hide hack 时触发），
        # 冷启动下重建落在绘制之前会无效，残留白板
        _reassert_widget_transparency(window, delay=0.15)

    window.events.shown += _on_shown
    window.events.restored += _on_restored
    window.events.loaded += _on_loaded
    webview.start()


if __name__ == '__main__':
    main()
