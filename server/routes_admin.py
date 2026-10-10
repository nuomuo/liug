"""管理端路由（/admin 前缀：用户管理 API + 独立管理前端托管；仅远程后端装配）

- 仅 server/app.py 以 extra_routers 装配；桌面端不 import 本模块，exe 不打包（liug.spec excludes 兜底）
- 双重防线：
  1. IP 白名单：环境变量 LIUG_ADMIN_ALLOWED_IPS（逗号分隔 IP 或 CIDR；**未配置或为空时不做限制**，
     一旦配置则仅放行名单内来源；'*' 表示不限制，仅建议内网使用）。注意反向代理部署时
     request.client 是代理地址，需把代理 IP 加入白名单或改用直连端口访问。
  2. 会话 + role=admin：复用 users.py 的 HMAC 会话体系（同 liug_session cookie），与主应用登录态互通；
     管理端使用独立登录端点 /admin/login（登录时即校验管理员角色）。
- 管理前端为独立 SPA（admin_client/，Vue3 + Vite），构建产物 admin_client/dist 在 /admin/ 路径下托管，
  与 client/（主应用）完全隔离，不进入桌面打包链路。开发模式：admin_client npm run dev（5181 端口，
  /admin 代理到 4300）。
- 保护规则：不能对自己执行禁用/降级/删除；系统至少保留一个可用管理员；重置密码后目标用户全部会话失效。
"""
import ipaddress
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

import users
from core.errors import ApiError

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[1]
USERNAME_MAX = 64


def _admin_dist_dir() -> Path:
    d = os.environ.get('LIUG_ADMIN_DIST_DIR')
    return Path(d).resolve() if d else (ROOT_DIR / 'admin_client' / 'dist')


# ---------- 防线一：IP 白名单（未配置或为空 = 不限制；配置后仅放行名单内 IP/CIDR，'*' 全放行） ----------
def _ip_allowed(host: str) -> bool:
    raw = (os.environ.get('LIUG_ADMIN_ALLOWED_IPS') or '').strip()
    if not raw:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for entry in raw.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if entry == '*':
            return True
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _check_admin_ip(request: Request):
    host = request.client.host if request.client else ''
    if not _ip_allowed(host):
        raise ApiError(403, '当前 IP 不在管理端白名单内（服务器环境变量 LIUG_ADMIN_ALLOWED_IPS）')


# ---------- 防线二：会话 + 管理员角色 ----------
def get_admin_user(request: Request):
    _check_admin_ip(request)
    token = request.cookies.get(users.SESSION_COOKIE)
    session = users.verify_session_token(token)
    if not session:
        raise ApiError(401, '未登录或会话已过期')
    user = users.find_user_by_id(session['uid'])
    if not user:
        raise ApiError(401, '账户不存在')
    if user['disabled']:
        raise ApiError(403, '账户已被禁用')
    if users.is_session_revoked(token) or (user['sessions_since'] or 0) > session['iat']:
        raise ApiError(401, '会话已失效，请重新登录')
    if user['role'] != 'admin':
        raise ApiError(403, '仅管理员可访问管理端')
    return user


# ---------- 管理端认证（独立登录页） ----------
@router.post('/admin/login')
def admin_login(request: Request, payload: dict = Body(default={})):
    _check_admin_ip(request)
    user = users.find_user_by_username(payload.get('username'))
    if not user or not users.verify_password(payload.get('password'), user['password_hash']):
        raise ApiError(401, '用户名或密码错误')
    if user['disabled']:
        raise ApiError(403, '账户已被禁用')
    if user['role'] != 'admin':
        raise ApiError(403, '该账户不是管理员，无法登录管理端')
    resp = JSONResponse({'user': users.public_user(user)})
    resp.set_cookie(
        users.SESSION_COOKIE, users.sign_session(user['id']),
        path='/', httponly=True, samesite='lax', max_age=users.SESSION_TTL,
    )
    return resp


@router.post('/admin/logout')
def admin_logout(request: Request):
    users.revoke_session(request.cookies.get(users.SESSION_COOKIE))
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(users.SESSION_COOKIE, path='/', httponly=True, samesite='lax')
    return resp


@router.get('/admin/me')
def admin_me(user=Depends(get_admin_user)):
    return {'user': users.public_user(user)}


@router.post('/admin/change-password')
def admin_change_password(payload: dict = Body(default={}), admin=Depends(get_admin_user)):
    """管理员修改自己的密码（与主应用 /api/auth/change-password 口径一致：
    验证原密码 → 更新哈希 → 吊销全部旧会话 → 重签当前会话，管理端不被踢出）"""
    if not users.verify_password(payload.get('oldPassword'), admin['password_hash']):
        raise ApiError(400, '原密码错误')
    new_password = payload.get('newPassword')
    if not isinstance(new_password, str) or len(new_password) < 6:
        raise ApiError(400, '新密码至少需要 6 个字符')
    users.update_password_hash(admin['id'], users.hash_password(new_password))
    users.revoke_all_sessions(admin['id'])
    resp = JSONResponse({'ok': True})
    resp.set_cookie(
        users.SESSION_COOKIE, users.sign_session(admin['id']),
        path='/', httponly=True, samesite='lax', max_age=users.SESSION_TTL,
    )
    return resp


# ---------- 用户管理 API ----------
def _clean_username(username):
    name = str(username or '').strip()
    if not name:
        raise ApiError(400, '用户名不能为空')
    if len(name) > USERNAME_MAX:
        raise ApiError(400, f'用户名不能超过 {USERNAME_MAX} 个字符')
    return name


def _clean_password(password):
    if not isinstance(password, str) or len(password) < 6:
        raise ApiError(400, '密码至少需要 6 个字符')
    return password


def _guard_last_admin(target):
    """保证系统始终至少保留一个可用（未禁用）的管理员"""
    if target['role'] == 'admin' and users.admin_count() <= 1:
        raise ApiError(400, '系统至少需要保留一个可用的管理员账户')


@router.get('/admin/users')
def admin_list_users(_=Depends(get_admin_user)):
    return {'users': [users.public_user(u) for u in users.list_users()]}


@router.post('/admin/users')
def admin_create_user(payload: dict = Body(default={}), _=Depends(get_admin_user)):
    username = _clean_username(payload.get('username'))
    password = _clean_password(payload.get('password'))
    role = 'admin' if payload.get('role') == 'admin' else 'user'
    if users.find_user_by_username(username):
        raise ApiError(400, '用户名已存在')
    uid = str(uuid.uuid4())
    users.insert_user(uid, username, users.hash_password(password), role)
    return {'user': users.public_user(users.find_user_by_id(uid))}


@router.patch('/admin/users/{uid}')
def admin_update_user(uid: str, payload: dict = Body(default={}), admin=Depends(get_admin_user)):
    target = users.find_user_by_id(uid)
    if not target:
        raise ApiError(404, '用户不存在')

    # 先整体校验、后写入，避免部分字段写入后因后续校验失败造成状态不一致
    new_username = payload.get('username')
    if new_username is not None:
        new_username = _clean_username(new_username)
        exists = users.find_user_by_username(new_username)
        if exists and exists['id'] != uid:
            raise ApiError(400, '用户名已存在')
    new_password = payload.get('password')
    if new_password is not None:
        new_password = _clean_password(new_password)
    new_role = payload.get('role')
    if new_role is not None and new_role not in ('admin', 'user'):
        raise ApiError(400, '角色只能是 admin 或 user')
    new_disabled = payload.get('disabled')
    if new_disabled is not None:
        new_disabled = bool(new_disabled)

    demote = new_role == 'user' and target['role'] == 'admin'
    if (demote or new_disabled is True) and target['id'] == admin['id']:
        raise ApiError(400, '不能对当前登录账户执行禁用或降级操作')
    if demote or new_disabled is True:
        _guard_last_admin(target)

    if new_username is not None:
        users.update_username(uid, new_username)
    if new_role is not None:
        users.update_role(uid, new_role)
    if new_disabled is not None:
        users.update_disabled(uid, new_disabled)
    if new_password is not None:
        users.update_password_hash(uid, users.hash_password(new_password))
        users.revoke_all_sessions(uid)  # 重置密码后目标用户的既有会话立即全部失效
    return {'user': users.public_user(users.find_user_by_id(uid))}


@router.delete('/admin/users/{uid}')
def admin_delete_user(uid: str, admin=Depends(get_admin_user)):
    target = users.find_user_by_id(uid)
    if not target:
        raise ApiError(404, '用户不存在')
    if target['id'] == admin['id']:
        raise ApiError(400, '不能删除当前登录的账户')
    _guard_last_admin(target)
    users.delete_user_row(uid)
    # 注：只删除账户记录，用户数据文件 data/users/<uid>.db 保留不动（可追溯/恢复）
    return {'ok': True}


# ---------- 管理前端静态托管（必须注册在 API 路由之后，避免吞掉 /admin/users 等 GET 端点） ----------
@router.get('/admin', include_in_schema=False)
@router.get('/admin/', include_in_schema=False)
@router.get('/admin/{path:path}', include_in_schema=False)
def admin_spa(request: Request, path: str = ''):
    _check_admin_ip(request)
    dist = _admin_dist_dir()
    if not (dist / 'index.html').is_file():
        raise ApiError(404, '管理前端未构建：请在 admin_client/ 目录执行 npm install && npm run build')
    candidate = None
    if path:
        candidate = (dist / path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            candidate = None  # 防目录穿越
    if candidate and candidate.is_file():
        return FileResponse(candidate)
    # index.html 每次回源校验（与主应用口径一致），静态资源带 hash 可安全长缓存
    return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})
