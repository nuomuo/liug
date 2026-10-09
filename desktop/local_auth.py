"""桌面客户端本地认证（单机免登录 + 云端账号代理；用户管理逻辑不进 exe）

- 单机模式：无账户无密码，POST /api/auth/local 免密签发固定 LOCAL_UID 会话，
  业务数据在 <LIUG_USERS_DIR>/local.db 单文件中，与云端镜像互不相干；
- 云端账号：POST /api/auth/remote 由本地服务代理登录远程服务器（WebView 永远留在本地
  origin，不整页跳转）。远程令牌存 <data>/remote-session.json，本地签发 uid=远程用户 ID
  的会话——数据落在本地镜像库 <LIUG_USERS_DIR>/<远程ID>.db（断网可用），联网后由
  desktop/sync.py 与服务端双向同步；
- 会话：与服务端同一套契约（cookie 名 liug_session、HMAC 签名令牌、相同响应形状），
  密钥在 <data>/local.secret——前端因此完全无需改动；
- /api/auth/me 返回的 user 带 mode：'standalone'（单机）或 'cloud'（云端账号），
  前端据此区分形态；登出为进程内内存吊销 + 清除远程会话记录
"""
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from core.auth import sign_session, token_sig, verify_session_token
from core.errors import ApiError

ROOT_DIR = Path(__file__).resolve().parents[1]

LOCAL_UID = 'local'
SESSION_COOKIE = 'liug_session'
LOCAL_SESSION_TTL = 3650 * 24 * 3600  # 单机免登录：10 年（点一次「单机使用」后跨重启免登录）
CLOUD_SESSION_TTL = 30 * 24 * 3600    # 云端账号本地会话：30 天（远程令牌仅 7 天，过期只影响同步，离线使用不受影响）
REMOTE_LOGIN_TIMEOUT = 10.0

_lock = threading.RLock()
_revoked = set()  # 本进程内已登出的令牌签名段


def _data_dir() -> Path:
    env = os.environ.get('LIUG_DATA_DIR')
    return Path(env).resolve() if env else (ROOT_DIR / 'data')


def _secret_file() -> Path:
    return _data_dir() / 'local.secret'


def _config_file() -> Path:
    return _data_dir() / 'config.json'


def _remote_session_file() -> Path:
    return _data_dir() / 'remote-session.json'


def _load_secret() -> str:
    p = _secret_file()
    if p.exists():
        s = p.read_text(encoding='utf-8').strip()
        if s:
            return s
    import secrets
    s = secrets.token_hex(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding='utf-8')
    return s


def _load_remote_url() -> str:
    """已配置的远程服务地址（空串 = 未配置）"""
    try:
        d = json.loads(_config_file().read_text(encoding='utf-8'))
        u = str(d.get('remoteUrl') or '').strip().rstrip('/')
        return u if _valid_remote_url(u) else ''
    except Exception:
        return ''


def _save_remote_url(url: str):
    with _lock:
        try:
            cfg = json.loads(_config_file().read_text(encoding='utf-8'))
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}
        cfg['remoteUrl'] = url
        _config_file().parent.mkdir(parents=True, exist_ok=True)
        _config_file().write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')


def _valid_remote_url(u) -> bool:
    try:
        p = urlparse(str(u))
        return p.scheme in ('http', 'https') and bool(p.netloc)
    except Exception:
        return False


# ---------- 远程会话记录（云端账号） ----------
def load_remote_session():
    """已保存的远程会话 {remoteUrl, uid, username, role, token, savedAt}；无或损坏返回 None"""
    try:
        d = json.loads(_remote_session_file().read_text(encoding='utf-8'))
        if isinstance(d, dict) and d.get('uid') and d.get('token') and _valid_remote_url(d.get('remoteUrl')):
            return d
    except Exception:
        pass
    return None


def _save_remote_session(d: dict):
    with _lock:
        _remote_session_file().parent.mkdir(parents=True, exist_ok=True)
        _remote_session_file().write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')


def _clear_remote_session():
    with _lock:
        try:
            _remote_session_file().unlink()
        except FileNotFoundError:
            pass


def ensure_local_secret():
    """初始化会话密钥（桌面端内嵌服务启动前调用）"""
    with _lock:
        _load_secret()


router = APIRouter(prefix='/api')


def get_user_id(request: Request) -> str:
    """业务端点的鉴权依赖：校验本地会话，返回用户库 ID（单机固定 LOCAL_UID / 云端为远程用户 ID）"""
    token = request.cookies.get(SESSION_COOKIE)
    session = verify_session_token(token, _load_secret())
    if not session or token_sig(token) in _revoked:
        raise ApiError(401, '未登录或会话已过期')
    if session['uid'] == LOCAL_UID:
        return LOCAL_UID
    # 云端会话：uid 必须与已保存的远程会话一致（登出即清除记录，令牌随之失效）
    rs = load_remote_session()
    if rs and rs['uid'] == session['uid']:
        return session['uid']
    raise ApiError(401, '远程账号会话已失效，请重新登录')


def _public_user():
    return {
        'id': LOCAL_UID,
        'username': '本地用户',
        'role': 'user',
        'disabled': False,
        'mode': 'standalone',  # 前端据此识别单机模式（远程端 user 无此字段）
    }


def _cloud_user():
    rs = load_remote_session()
    if not rs:
        raise ApiError(401, '远程账号会话已失效，请重新登录')
    return {
        'id': rs['uid'],
        'username': rs.get('username') or '云端用户',
        'role': rs.get('role') or 'user',
        'disabled': False,
        'mode': 'cloud',  # 前端据此识别云端账号（本地镜像 + 双向同步）
        'remoteUrl': rs['remoteUrl'],
    }


def _set_cookie(resp, uid, ttl):
    resp.set_cookie(
        SESSION_COOKIE, sign_session(uid, _load_secret(), ttl=ttl),
        path='/', httponly=True, samesite='lax', max_age=ttl,
    )


@router.post('/auth/local')
def login_local():
    """进入单机模式：免密签发本地会话（仅桌面端有此端点，远程服务端不注册）"""
    resp = JSONResponse({'user': _public_user()})
    _set_cookie(resp, LOCAL_UID, LOCAL_SESSION_TTL)
    return resp


@router.post('/auth/remote')
def login_remote(payload: dict = Body(default={})):
    """登录云端账号：本地服务代理远程登录，之后 WebView 保持在本地 origin 操作本地镜像库

    成功后：远程令牌存 <data>/remote-session.json（同步引擎用），本地签发 uid=远程用户 ID
    的会话（镜像库 <LIUG_USERS_DIR>/<远程ID>.db 与单机 local.db 完全独立）。
    """
    remote_url = str(payload.get('remoteUrl') or '').strip().rstrip('/')
    username = str(payload.get('username') or '').strip()
    password = str(payload.get('password') or '')
    if not _valid_remote_url(remote_url):
        raise ApiError(400, '服务器地址格式不正确，应形如 https://example.com')
    if not username or not password:
        raise ApiError(400, '请输入用户名和密码')
    try:
        r = httpx.post(remote_url + '/api/auth/login',
                       json={'username': username, 'password': password},
                       timeout=REMOTE_LOGIN_TIMEOUT)
    except httpx.HTTPError:
        raise ApiError(502, '无法连接服务器，请检查网络或服务器地址')
    if r.status_code == 401:
        raise ApiError(401, '用户名或密码错误')
    if r.status_code != 200:
        raise ApiError(502, f'服务器登录失败（HTTP {r.status_code}）')
    try:
        user = (r.json() or {}).get('user') or {}
    except Exception:
        user = {}
    token = r.cookies.get(SESSION_COOKIE)
    uid = user.get('id')
    if not token or not uid:
        raise ApiError(502, '服务器响应异常，请确认地址为流光 LIUG 服务端')
    _save_remote_session({
        'remoteUrl': remote_url, 'uid': uid, 'username': user.get('username') or username,
        'role': user.get('role') or 'user', 'token': token, 'savedAt': int(time.time() * 1000),
    })
    _save_remote_url(remote_url)  # 记住服务器地址，登录页下次预填
    # 立即以 seed=False 初始化镜像库并加入连接缓存：后续业务路由 / 同步引擎共用此缓存，
    # 镜像库内容 100% 来自首次同步（否则首个业务请求会播种默认清单，污染与老服务端库的合并）
    from core.db import user_db_ctx
    with user_db_ctx(uid, seed=False):
        pass
    resp = JSONResponse({'user': _cloud_user()})
    _set_cookie(resp, uid, CLOUD_SESSION_TTL)
    _kick_sync_engine()  # 登录成功立即做初始同步（首拉远程数据填充镜像库）
    return resp


def _kick_sync_engine():
    """通知同步引擎（延迟导入避免循环依赖；引擎未初始化时静默跳过）"""
    try:
        import sync
        engine = sync.get_engine()
        if engine:
            engine.notify_change()
    except Exception:
        pass


@router.post('/auth/logout')
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    session = verify_session_token(token, _load_secret())
    if session and session['uid'] != LOCAL_UID:
        _clear_remote_session()  # 云端登出：清除远程会话记录（镜像库保留，下次登录续用）
    sig = token_sig(token)
    if sig:
        _revoked.add(sig)
        if len(_revoked) > 1000:
            _revoked.clear()  # 极端场景防膨胀（单机会话有效期长，登出依赖内存吊销）
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax')
    return resp


@router.get('/auth/me')
def me(uid: str = Depends(get_user_id)):
    if uid == LOCAL_UID:
        return {'user': _public_user()}
    return {'user': _cloud_user()}


@router.get('/desktop/config')
def get_config():
    """桌面端配置（登录页据此区分本地/远程环境并读取远程服务地址）"""
    return {'remoteUrl': _load_remote_url()}


@router.put('/desktop/config')
def put_config(payload: dict = Body(default={})):
    """保存远程服务地址（登录前可用，无需会话）"""
    url = str(payload.get('remoteUrl') or '').strip().rstrip('/')
    if url and not _valid_remote_url(url):
        raise ApiError(400, '服务器地址格式不正确，应形如 https://example.com')
    _save_remote_url(url)
    return {'remoteUrl': url}
