"""流光 LIUG 桌面版启动器（系统托盘 + 主界面窗口 + 可选桌面四象限小组件）

本目录为桌面客户端外壳，**不包含用户管理逻辑**（账户体系仅在 server/ 远程后端）：
- 单机模式：免登录（desktop/local_auth.py 的 /api/auth/local 免密签发会话），
  业务数据在 <LIUG_USERS_DIR>/local.db 单文件中；
- 云端账号：本地服务代理登录远程服务器（/api/auth/remote），数据落在本地镜像库
  <LIUG_USERS_DIR>/<远程用户ID>.db（断网可用），联网后由 desktop/sync.py 与服务端
  双向同步（自动 + 手动）；两种模式的数据完全独立；
- 业务核心复用 core/（与远程后端同一份代码）。

一个进程搞定全部：
- 内嵌 uvicorn 服务（粘性动态端口：上次端口 → 4300 → 随机，bind 即占有并记录到
  data/service-port.json 供小组件发现），托管主应用前端与 API；
- 系统托盘常驻（pystray）：双击图标或菜单「打开流光 LIUG」显示主窗口，右键菜单可开关
  「桌面小组件（四象限）」，「退出」彻底结束进程；
- 主窗口点 × 仅隐藏到托盘（托盘应用惯例），从托盘「退出」才真正退出；
- Windows 互斥体单实例锁，重复启动弹提示退出，避免双进程写 SQLite。

启动：python desktop/main.py
测试数据目录：$env:LIUG_DATA_DIR='<临时目录>'; $env:LIUG_USERS_DIR='<临时目录>/users'; python desktop/main.py
打包：python -m PyInstaller --noconfirm liug.spec（产物 dist/liug.exe）
"""
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

# PyInstaller 冻结模式（liug.exe）：
# - 数据目录默认放在 exe 同级 data/ 下（可用 LIUG_DATA_DIR / LIUG_USERS_DIR 覆盖）
# - 静态资源指向 _MEIPASS 解包目录内打包的 client/dist 副本
if getattr(sys, 'frozen', False):
    _EXE_DIR = Path(sys.executable).resolve().parent
    _MEIPASS = Path(sys._MEIPASS)
    os.environ.setdefault('LIUG_DATA_DIR', str(_EXE_DIR / 'data'))
    os.environ.setdefault('LIUG_USERS_DIR', str(_EXE_DIR / 'data' / 'users'))
    os.environ.setdefault('LIUG_DIST_DIR', str(_MEIPASS / 'client' / 'dist'))
    # 无控制台模式（console=False）下 sys.stdout/stderr 为 None，
    # pythonnet/clr_loader 初始化或日志写入会因 None 崩溃导致进程静默退出——必须替换掉
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        try:
            (_EXE_DIR / 'data').mkdir(parents=True, exist_ok=True)
            sys.stderr = open(_EXE_DIR / 'data' / 'desktop.err.log', 'a', encoding='utf-8', buffering=1)
        except Exception:
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')
else:
    _EXE_DIR = None

# 开发模式：让 desktop/ 内模块能找到根目录的 core 包（冻结模式由 PyInstaller pathex 处理）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from widget_window import MoveSession, ResizeSession  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = '流光'
PREFERRED_PORT = 4300
MUTEX_NAME = 'Global\\LiugDesktopAppSingleInstance'

# 桌面小组件窗口尺寸上下限（拖拽边缘/角落缩放与 API 缩放共用同一上下限）
WIDGET_MIN_SIZE = (420, 320)
WIDGET_MAX_SIZE = (1100, 900)
WIDGET_DEFAULT_SIZE = (560, 440)
WIDGET_TITLE = '四象限'  # Win32 窗口标题：ctypes FindWindowW 按标题定位用于置顶切换

_state = {'main': None, 'widget': None, 'widget_api': None, 'icon': None, 'server': None, 'base_url': '', 'quitting': False}


def _data_dir() -> Path:
    env = os.environ.get('LIUG_DATA_DIR')
    if env:
        return Path(env)
    return (_EXE_DIR if _EXE_DIR else BASE_DIR.parent) / 'data'


def _widget_state_file() -> Path:
    """小组件窗口状态持久化文件（位置/尺寸/置顶）：data/widget.json"""
    return _data_dir() / 'widget.json'


def _load_widget_state() -> dict:
    try:
        data = json.loads(_widget_state_file().read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_widget_state(**kv) -> None:
    """合并写入小组件状态（单键更新不影响其他字段）"""
    st = _load_widget_state()
    st.update(kv)
    try:
        _data_dir().mkdir(parents=True, exist_ok=True)
        _widget_state_file().write_text(json.dumps(st), encoding='utf-8')
    except Exception:
        pass


def _save_widget_geometry() -> None:
    """记录小组件当前屏幕位置与尺寸（关闭/退出前调用，下次打开原位恢复）"""
    w = _state['widget']
    api = _state.get('widget_api')
    if not w:
        return
    try:
        kv = {'x': int(w.x), 'y': int(w.y)}
        if api:
            kv.update(w=api._size[0], h=api._size[1])
        _write_widget_state(**kv)
        _log(f'小组件状态已保存 {kv}')
    except Exception:
        pass


def _set_widget_topmost(pin: bool) -> bool:
    """ctypes 切换小组件置顶（pywebview 无运行期 pin 接口，按 Win32 标题找窗口）"""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, WIDGET_TITLE)
        if not hwnd:
            return False
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
        # HWND_TOPMOST/HWND_NOTOPMOST 为特殊伪句柄 -1/-2（64 位下即符号扩展的全 F）
        user32.SetWindowPos.restype = ctypes.c_bool
        return bool(user32.SetWindowPos(
            ctypes.c_void_p(hwnd), ctypes.c_void_p(-1 if pin else -2),
            0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE))
    except Exception:
        return False


def _clamp_widget_pos(x: int, y: int, w: int, h: int):
    """位置恢复时夹在虚拟屏幕可见范围内（多显示器/分辨率变化后不丢窗口）"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        if vw > 0 and vh > 0:
            x = min(max(vx, x), vx + vw - w)
            y = min(max(vy, y), vy + vh - h)
    except Exception:
        pass
    return x, y


def _log(msg: str) -> None:
    """运行日志：data/desktop.log（无控制台的 exe 场景排查用），同时 print"""
    line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(line)
    try:
        log_dir = _data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / 'desktop.log', 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def _install_excepthooks() -> None:
    """把未捕获异常写进运行日志（windowed exe 弹窗之外留档）"""
    import traceback

    def _hook(t, v, tb):
        _log('未捕获异常:\n' + ''.join(traceback.format_exception(t, v, tb)))

    sys.excepthook = _hook
    threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)


def _acquire_single_instance() -> bool:
    """Windows 互斥体单实例锁；非首实例时弹框提示后返回 False"""
    if sys.platform != 'win32':
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            0, f'{APP_NAME}已在运行，请查看任务栏右下角托盘图标。', APP_NAME, 0x40)
        return False
    return True


def _service_port_file() -> Path:
    """粘性端口记录文件（data/service-port.json）：小组件据此发现主服务"""
    return _data_dir() / 'service-port.json'


def _load_saved_port() -> int:
    try:
        d = json.loads(_service_port_file().read_text(encoding='utf-8'))
        p = int(d['port'])
        return p if 1024 <= p <= 65535 else 0
    except Exception:
        return 0


def _bind_service_socket() -> socket.socket:
    """绑定服务端口（粘性策略：上次端口 → 4300 → 随机）

    直接以 socket bind 占有端口后交给 uvicorn（serve(sockets=...)），消除
    「探测可用与实际监听之间被其他程序抢占」的竞态窗口。粘性策略保端口跨重启稳定，
    WebView 的 localStorage（主题色等）按 origin 隔离，端口跳变会导致数据"丢失"。
    """
    for port in (_load_saved_port(), PREFERRED_PORT):
        if port:
            try:
                s = socket.socket()
                s.bind(('127.0.0.1', port))
                return s
            except OSError:
                continue
    s = socket.socket()
    s.bind(('127.0.0.1', 0))  # 系统分配随机可用端口
    return s


def _wait_ready(base_url: str, timeout: float = 15.0) -> None:
    """轮询探活，等内嵌服务可对外响应（/api/auth/me 200/401 即就绪）"""
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(base_url + '/api/auth/me', timeout=1).status_code in (200, 401):
                return
        except Exception:
            pass
        time.sleep(0.15)
    raise RuntimeError('内嵌服务启动超时')


def _build_app():
    """组装桌面端 FastAPI 应用：core 业务核心 + 本地认证（单机/云端）+ 云端同步引擎"""
    from core.app_factory import create_app
    from local_auth import get_user_id, router as auth_router
    from sync import init_engine, router as sync_router
    # extra_routers 在 SPA catch-all 之前注册（后 include 的 GET 会被 fallback 吞掉）
    app = create_app(get_user_id, auth_router, extra_routers=[sync_router])
    init_engine(_data_dir()).start()  # 同步引擎随主服务启动（云端账号登录后生效）
    return app


def _start_server():
    """内嵌 uvicorn（粘性动态端口：上次端口 → 4300 → 随机，bind 即占有），返回 (server, base_url)"""
    app = _build_app()
    sock = _bind_service_socket()
    port = sock.getsockname()[1]
    try:
        _data_dir().mkdir(parents=True, exist_ok=True)
        _service_port_file().write_text(json.dumps({'port': port, 'pid': os.getpid()}), encoding='utf-8')
    except Exception:
        pass
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
    # server.run 为同步入口（内部 asyncio.run(serve())）；serve() 本身是协程，不能直接做线程 target
    threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True, name='uvicorn').start()
    base_url = f'http://127.0.0.1:{port}'
    _wait_ready(base_url)
    return server, base_url


def make_app_icon(size: int = 64):
    """程序化绘制应用图标（蓝色圆角方块 + 白色对勾），托盘图标与 exe 图标共用"""
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, size - 1, size - 1], radius=int(size * 0.3), fill=(37, 99, 235, 255))
    lw = max(3, size // 8)
    d.line([(size * 0.26, size * 0.52), (size * 0.44, size * 0.69), (size * 0.76, size * 0.31)],
           fill=(255, 255, 255, 255), width=lw, joint='curve')
    return img


class _WidgetApi:
    """暴露给小组件前端的窗口控制（window.pywebview.api.*）"""

    def __init__(self):
        self._window = None
        self._size = list(WIDGET_DEFAULT_SIZE)  # 当前窗口尺寸（逻辑像素），拖拽缩放/API 缩放后同步
        self._resize = None  # 进行中的拖拽缩放会话（widget_window.ResizeSession）
        self._move = None    # 进行中的窗口拖动会话（widget_window.MoveSession）

    def close(self):
        if self._window:
            _save_widget_geometry()  # 记住当前位置/尺寸，下次打开原位恢复
            self._window.destroy()

    def minimize(self):
        if self._window:
            self._window.minimize()

    # ---- 标题栏拖动窗口（HTCAPTION 原生拖动在 WebView2 下不生效，改用与缩放同款的指针方案）----
    # 前端三步调用：begin_move() → update_move()（拖动中高频） → end_move()

    def begin_move(self):
        """开始拖动窗口：标题栏 pointerdown 时调用"""
        s = MoveSession(WIDGET_TITLE)
        self._move = s if s.begin() else None

    def update_move(self):
        """拖动中按光标增量平移窗口（每次 pointermove 调一次）"""
        if self._move:
            self._move.update()

    def end_move(self):
        """结束拖动：持久化最终位置"""
        if not self._move:
            return
        geo = self._move.end()
        self._move = None
        if geo:
            _write_widget_state(x=geo[0], y=geo[1])  # 记住位置，下次打开原位恢复

    def open_main(self):
        """小组件未登录时的「去登录」入口：打开（或还原）主界面窗口"""
        _open_main()

    def get_state(self):
        """小组件窗口状态（前端初始化图钉按钮等用）"""
        st = _load_widget_state()
        return {'pin': bool(st.get('pin')), 'size': [self._size[0], self._size[1]]}

    def toggle_pin(self):
        """切换置顶（默认不置顶，不挡其他应用；置顶状态持久化）"""
        pin = not bool(_load_widget_state().get('pin'))
        if _set_widget_topmost(pin):
            _write_widget_state(pin=pin)
            _log(f'小组件置顶切换 → {"置顶" if pin else "非置顶"}')
            return pin
        return None  # 窗口定位失败（如非 Windows）

    def resize(self, dw=0, dh=0, w=None, h=None):
        """调整小组件窗口尺寸（像素）：传 w/h 直接设置，传 dw/dh 按增量调整，夹在上下限内"""
        if not self._window:
            return None
        if w is None or h is None:
            w, h = self._size[0] + int(dw), self._size[1] + int(dh)
        w = max(WIDGET_MIN_SIZE[0], min(WIDGET_MAX_SIZE[0], int(w)))
        h = max(WIDGET_MIN_SIZE[1], min(WIDGET_MAX_SIZE[1], int(h)))
        self._size = [w, h]
        self._window.resize(w, h)
        _write_widget_state(w=w, h=h)  # 记住尺寸，下次打开保持
        return [w, h]

    # ---- 拖拽边缘/角落缩放（frameless 窗口原生不支持，用 Win32 补齐，见 widget_window.py）----
    # 前端三步调用：begin_resize(edge) → update_resize()（拖动中高频） → end_resize()

    def begin_resize(self, edge):
        """开始一次拖拽缩放：edge 为 n/s/e/w/ne/nw/se/sw"""
        s = ResizeSession(WIDGET_TITLE, WIDGET_MIN_SIZE, WIDGET_MAX_SIZE)
        self._resize = s if s.begin(edge) else None

    def update_resize(self):
        """拖动过程中按光标增量移动+缩放窗口（每次 pointermove 调一次）"""
        if self._resize:
            self._resize.update()

    def end_resize(self):
        """结束拖拽：同步内存尺寸并持久化最终位置/尺寸"""
        if not self._resize:
            return
        geo = self._resize.end()
        self._resize = None
        if geo:
            x, y, w, h = geo
            self._size = [w, h]
            _write_widget_state(x=x, y=y, w=w, h=h)


def _widget_alive() -> bool:
    import webview
    w = _state['widget']
    return w is not None and w in webview.windows


def _dist_version() -> str:
    """取 client/dist/index.html 的 mtime 作为版本号：附加到加载 URL 上破 WebView2 持久缓存。

    WebView2 用户数据目录（%APPDATA%/pywebview）是持久的，对无缓存头的旧版 index.html
    存在启发式缓存——即便服务端已改为 no-cache，旧条目仍可能在过期前一直被直接命中。
    URL 不同即绕过缓存；mtime 随每次前端构建变化，天然单调。
    """
    try:
        dist = Path(os.environ.get('LIUG_DIST_DIR') or (BASE_DIR.parent / 'client' / 'dist'))
        return str(int((dist / 'index.html').stat().st_mtime))
    except OSError:
        return '0'


def _create_main_window(base_url):
    import webview
    w = webview.create_window(APP_NAME, f'{base_url}/?v={_dist_version()}',
                              width=1280, height=860, min_size=(960, 640))
    _state['main'] = w

    def _on_closing():
        if not _state['quitting']:
            _log('主窗口关闭请求 → 隐藏到托盘')
            w.hide()
            return False  # 取消关闭：隐藏到托盘继续驻留
        _log('主窗口关闭请求 → 退出流程放行')
        return True  # 托盘「退出」放行销毁

    w.events.closing += _on_closing


def _create_widget_window(base_url, rebuild=False):
    import webview
    if _widget_alive():
        try:
            _state['widget'].restore()  # 若此前被最小化，先还原（restored 处理器会顺带修复透明）
        except Exception:
            pass
        _state['widget'].show()
        return
    # 恢复上次的位置/尺寸（首次打开用默认值）
    st = _load_widget_state()
    w, h = int(st.get('w') or 0), int(st.get('h') or 0)
    if not (WIDGET_MIN_SIZE[0] <= w <= WIDGET_MAX_SIZE[0]):
        w = WIDGET_DEFAULT_SIZE[0]
    if not (WIDGET_MIN_SIZE[1] <= h <= WIDGET_MAX_SIZE[1]):
        h = WIDGET_DEFAULT_SIZE[1]
    pos = {}
    if isinstance(st.get('x'), int) and isinstance(st.get('y'), int):
        pos['x'], pos['y'] = _clamp_widget_pos(st['x'], st['y'], w, h)
    api = _WidgetApi()
    api._size = [w, h]
    win = webview.create_window(
        WIDGET_TITLE, f'{base_url}/quadrant?v={_dist_version()}', width=w, height=h,
        min_size=WIDGET_MIN_SIZE, **pos,
        frameless=True,   # 无边框：UI 完全由前端面板绘制
        transparent=True,  # 透明背景：只显示小组件面板本体
        on_top=False,     # 默认不置顶，不遮挡其他应用；置顶由标题栏图钉按钮切换（持久化）
        easy_drag=False,  # 必须显式关闭（默认 True！）：其监听任意 mousedown，会与页面内
        # 拖任务/缩放手柄冲突（HTML5 拖拽吞掉 mouseup 后窗口跟着鼠标跑）；拖动改由标题栏 begin/update/end_move API 实现
        js_api=api,
    )
    api._window = win
    _state['widget'] = win
    _state['widget_api'] = api

    def _on_shown():
        # 上次是置顶状态则恢复（Win32 层切换，见 _set_widget_topmost）
        if st.get('pin'):
            _set_widget_topmost(True)
        if rebuild:
            # pywebview 的透明窗口 hack（创建时 Show→Hide）只在 webview.start() 时生效，
            # 托盘动态重建的窗口透明合成失效，shown 后 hide→show 强制重建一次
            time.sleep(0.2)
            try:
                win.hide()
                time.sleep(0.3)
                win.show()
            except Exception:
                pass

    def _on_restored():
        # WebView2 透明窗口最小化再还原后透明合成会失效（面板背后露出窗体底色，
        # 半透明面板/按钮视觉全变），hide→show 一次强制重建合成层即可恢复
        # （与 pywebview 初始化透明窗口时的 Show/Hide hack 同理）
        time.sleep(0.2)  # 等还原动画结束、窗口状态稳定
        try:
            win.hide()
            time.sleep(0.3)
            win.show()
        except Exception:
            pass

    win.events.shown += _on_shown
    win.events.restored += _on_restored


def _open_main():
    w = _state['main']
    if w:
        w.show()
        try:
            w.restore()  # 若此前被最小化则还原
        except Exception:
            pass


def _toggle_widget():
    if _widget_alive():
        _log('托盘：关闭桌面小组件')
        _save_widget_geometry()  # 记住位置，托盘菜单再打开时原位恢复
        try:
            _state['widget'].destroy()
        except Exception:
            pass
        _state['widget'] = None
    else:
        _log('托盘：打开桌面小组件')
        _create_widget_window(_state['base_url'], rebuild=True)


def _quit():
    """托盘「退出」/全部窗口销毁后的统一收尾：停服务、关窗口、停托盘"""
    import webview
    _log('退出流程开始')
    _state['quitting'] = True
    _save_widget_geometry()  # 退出前记住小组件位置/尺寸
    if _state['server'] is not None:
        _state['server'].should_exit = True
    for w in list(webview.windows):
        try:
            w.destroy()
        except Exception:
            pass
    if _state['icon'] is not None:
        try:
            _state['icon'].stop()
        except Exception:
            pass


def main():
    try:
        import webview
        import pystray
    except ImportError as e:
        raise SystemExit(f'缺少依赖 {e.name}，请先执行：python -m pip install -r desktop/requirements.txt')

    _install_excepthooks()
    _log(f'启动（pid={os.getpid()} frozen={bool(_EXE_DIR)}）')

    if not _acquire_single_instance():
        _log('已有实例在运行，本次启动退出')
        return

    # 初始化本地会话密钥（单机免登录，无账户；不含任何用户管理逻辑）
    if not _EXE_DIR and not os.environ.get('LIUG_DATA_DIR'):
        print('[desktop] 提示：开发模式未设置 LIUG_DATA_DIR，将使用项目数据目录 data/（单机数据 local.db）')
    from local_auth import ensure_local_secret
    ensure_local_secret()

    server, base_url = _start_server()
    _state['server'] = server
    _state['base_url'] = base_url
    _log(f'内嵌服务已启动 {base_url}')

    # 系统托盘：双击 = 打开主界面；右键菜单可开关桌面小组件、退出
    menu = pystray.Menu(
        pystray.MenuItem(f'打开{APP_NAME}', lambda _item: _open_main(), default=True),
        pystray.MenuItem('显示桌面小组件（四象限）', lambda _item: _toggle_widget(),
                         checked=lambda _item: _widget_alive()),
        pystray.MenuItem('退出', lambda _item: _quit()),
    )
    icon = pystray.Icon('liug', make_app_icon(), APP_NAME, menu)
    _state['icon'] = icon
    icon.run_detached()

    # 主窗口（关闭=隐藏到托盘）+ 桌面小组件（默认展示，可在托盘菜单关闭）
    _create_main_window(base_url)
    _create_widget_window(base_url)

    # private_mode=False：保留 cookies/localStorage（登录状态、主题色等跨重启记忆），
    # storage_path 指到 exe 同级 data/webview，便携不污染系统浏览器配置
    webview_storage = _data_dir() / 'webview'
    webview_storage.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(webview_storage))  # 阻塞至所有窗口销毁（实际仅托盘「退出」会触发）
    _log('webview.start() 已返回，开始收尾')
    _quit()
    time.sleep(0.3)  # 给 uvicorn/托盘线程一点收尾时间
    _log('进程退出')
    sys.exit(0)


if __name__ == '__main__':
    main()
