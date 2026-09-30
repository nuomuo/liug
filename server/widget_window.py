"""小组件窗口 Win32 拖拽缩放辅助（仅 Windows，其他平台各方法安全返回失败）

pywebview 的 frameless 窗口不支持拖动边缘/角落调整大小，此处用 Win32 补齐：
前端在窗口四边/四角布置隐形手柄，pointerdown 时调 begin_resize(edge)，
拖动过程中高频调 update_resize()（按光标增量一次 SetWindowPos 完成移动+缩放），
pointerup 时调 end_resize() 拿最终几何（逻辑像素）做持久化。

光标增量用 GetCursorPos 取物理像素，不经 JS 坐标换算（Chromium 的 screenX 是
DIP，DPI 缩放下与 Win32 物理坐标不一致）；窗口尺寸上下限以逻辑像素传入，
内部按窗口 DPI 换算成物理像素再夹取。
"""
import ctypes
import sys

# 合法拖拽方向：北/南/东/西 与四个角的组合
EDGES = ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw')


class _POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def _user32():
    return ctypes.windll.user32 if sys.platform == 'win32' else None


def find_hwnd(title: str) -> int:
    """按窗口标题定位 HWND（pywebview 窗口标题即 Win32 标题）"""
    u = _user32()
    return u.FindWindowW(None, title) if u else 0


def get_window_rect(hwnd: int):
    """窗口几何 (x, y, w, h)，物理像素；失败返回 None"""
    u = _user32()
    rc = _RECT()
    if not u or not hwnd or not u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rc)):
        return None
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


def get_cursor_pos():
    """当前光标屏幕坐标 (x, y)，物理像素；失败返回 None"""
    u = _user32()
    pt = _POINT()
    if not u or not u.GetCursorPos(ctypes.byref(pt)):
        return None
    return pt.x, pt.y


def dpi_scale(hwnd: int) -> float:
    """窗口 DPI 缩放系数（96 基准）；取不到按 1.0"""
    u = _user32()
    try:
        return (u.GetDpiForWindow(ctypes.c_void_p(hwnd)) or 96) / 96.0
    except Exception:
        return 1.0


def set_window_rect(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    """一次完成移动+缩放（不动 z-order、不抢焦点）"""
    u = _user32()
    if not u:
        return False
    SWP_NOZORDER, SWP_NOACTIVATE = 0x4, 0x10
    u.SetWindowPos.restype = ctypes.c_bool
    return bool(u.SetWindowPos(ctypes.c_void_p(hwnd), None, x, y, w, h,
                               SWP_NOZORDER | SWP_NOACTIVATE))


class MoveSession:
    """一次窗口拖动会话：begin() → update()*N → end()（语义与 ResizeSession 一致）

    曾尝试 WM_NCLBUTTONDOWN/HTCAPTION 系统原生拖动，实测在 WebView2 下不生效
    （窗口收到消息但不进入移动循环），故改用与缩放同款的指针事件驱动方案。
    """

    def __init__(self, title: str):
        self._title = title
        self._hwnd = 0
        self._rect0 = None   # 拖动起点窗口几何（物理像素）
        self._pt0 = None     # 拖动起点光标（物理像素）

    def begin(self) -> bool:
        self._hwnd = find_hwnd(self._title)
        rect = get_window_rect(self._hwnd)
        cur = get_cursor_pos()
        if not rect or not cur:
            return False
        self._rect0, self._pt0 = rect, cur
        return True

    def update(self) -> bool:
        """窗口整体跟随光标增量平移，尺寸不变"""
        if not self._rect0 or not self._pt0:
            return False
        cur = get_cursor_pos()
        if not cur:
            return False
        x0, y0, w0, h0 = self._rect0
        return set_window_rect(self._hwnd,
                               x0 + cur[0] - self._pt0[0], y0 + cur[1] - self._pt0[1],
                               w0, h0)

    def end(self):
        """收尾：返回最终几何 (x, y, w, h)（逻辑像素，供持久化）；失败 None"""
        rect = get_window_rect(self._hwnd) if self._hwnd else None
        self._rect0 = self._pt0 = None
        if not rect:
            return None
        x, y, w, h = rect
        s = dpi_scale(self._hwnd)
        return round(x / s), round(y / s), round(w / s), round(h / s)


class ResizeSession:
    """一次拖拽缩放会话：begin(edge) → update()*N → end()"""

    def __init__(self, title: str, min_size, max_size):
        self._title = title
        self._min = tuple(min_size)   # 逻辑像素，与 pywebview 窗口尺寸同口径
        self._max = tuple(max_size)
        self._hwnd = 0
        self._edge = ''
        self._rect0 = None   # 拖拽起点窗口几何（物理像素）
        self._pt0 = None     # 拖拽起点光标（物理像素）

    def begin(self, edge: str) -> bool:
        if edge not in EDGES:
            return False
        self._hwnd = find_hwnd(self._title)
        rect = get_window_rect(self._hwnd)
        cur = get_cursor_pos()
        if not rect or not cur:
            return False
        self._edge, self._rect0, self._pt0 = edge, rect, cur
        return True

    def update(self) -> bool:
        """按当前光标增量调整窗口：东/南向只改尺寸，西/北向同时移动保持对边不动"""
        if not self._rect0 or not self._pt0:
            return False
        cur = get_cursor_pos()
        if not cur:
            return False
        x0, y0, w0, h0 = self._rect0
        dx, dy = cur[0] - self._pt0[0], cur[1] - self._pt0[1]
        s = dpi_scale(self._hwnd)
        minw, minh = int(self._min[0] * s), int(self._min[1] * s)
        maxw, maxh = int(self._max[0] * s), int(self._max[1] * s)
        w, h = w0, h0
        if 'e' in self._edge:
            w = w0 + dx
        if 's' in self._edge:
            h = h0 + dy
        if 'w' in self._edge:
            w = w0 - dx
        if 'n' in self._edge:
            h = h0 - dy
        w = max(minw, min(maxw, w))
        h = max(minh, min(maxh, h))
        x, y = x0, y0
        if 'w' in self._edge:
            x = x0 + (w0 - w)   # 宽度被夹住时左边缘停在极限处，右边缘继续跟光标
        if 'n' in self._edge:
            y = y0 + (h0 - h)
        return set_window_rect(self._hwnd, x, y, w, h)

    def end(self):
        """收尾：返回最终几何 (x, y, w, h)（逻辑像素，供持久化/尺寸跟踪）；失败 None"""
        rect = get_window_rect(self._hwnd) if self._hwnd else None
        self._rect0 = self._pt0 = None
        if not rect:
            return None
        x, y, w, h = rect
        s = dpi_scale(self._hwnd)
        return round(x / s), round(y / s), round(w / s), round(h / s)
