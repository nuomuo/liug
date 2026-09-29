"""/system/* 用户管理路由（由原 system-admin Flask 程序合并而来，口径与 Flask 版一致）

- 仅管理员可登录；使用独立 Cookie（dida_system_session）与独立密钥（users.db.system-secret）
- 复用用户主库的 revoked_sessions / sessions_since 会话失效机制
"""
import re
import uuid

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

import db
import users
from errors import ApiError

router = APIRouter(prefix='/system')

COOKIE = users.SYSTEM_SESSION_COOKIE
SECRET = users.SYSTEM_SECRET
USERNAME_RE = re.compile(r'^\S{2,32}$')


def invalid_username(username):
    return not isinstance(username, str) or not USERNAME_RE.match(username)


def get_admin(request: Request):
    """系统管理端鉴权：有效管理员会话，返回用户行"""
    token = request.cookies.get(COOKIE)
    session = users.verify_session_token(token, SECRET)
    if not session:
        raise ApiError(401, '未登录或会话已过期')
    if users.is_session_revoked(token):
        raise ApiError(401, '未登录或会话已过期')
    user = users.find_user_by_id(session['uid'])
    if not user or user['disabled']:
        raise ApiError(401, '未登录或会话已过期')
    if (user['sessions_since'] or 0) > session['iat']:
        raise ApiError(401, '未登录或会话已过期')  # 密码已被重置，旧会话失效
    if user['role'] != 'admin':
        raise ApiError(403, '需要管理员权限')
    return user


# ---------- 认证接口 ----------
@router.post('/auth/login')
def login(payload: dict = Body(default={})):
    user = users.find_user_by_username(payload.get('username'))
    if not user or not users.verify_password(payload.get('password'), user['password_hash']):
        raise ApiError(401, '用户名或密码错误')
    if user['disabled']:
        raise ApiError(403, '账户已被禁用')
    if user['role'] != 'admin':
        raise ApiError(403, '需要管理员权限')
    resp = JSONResponse({'user': users.public_user(user)})
    resp.set_cookie(
        COOKIE, users.sign_session(user['id'], SECRET),
        path='/', httponly=True, samesite='lax', max_age=users.SESSION_TTL,
    )
    return resp


@router.post('/auth/logout')
def logout(request: Request):
    users.revoke_session(request.cookies.get(COOKIE), SECRET)
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(COOKIE, path='/', httponly=True, samesite='lax')
    return resp


@router.get('/auth/me')
def me(admin=Depends(get_admin)):
    return {'user': users.public_user(admin)}


# ---------- 用户管理接口（仅管理员） ----------
@router.get('/users')
def list_users(admin=Depends(get_admin)):
    return {'users': [users.public_user(u) for u in users.list_users()]}


@router.post('/users')
def create_user(payload: dict = Body(default={}), admin=Depends(get_admin)):
    username = payload.get('username')
    password = payload.get('password')
    role = payload.get('role')
    if invalid_username(username):
        raise ApiError(400, '用户名需为 2-32 个字符且不含空白')
    if not isinstance(password, str) or len(password) < 6:
        raise ApiError(400, '密码至少需要 6 个字符')
    if users.find_user_by_username(username):
        raise ApiError(400, '用户名已存在')
    uid = str(uuid.uuid4())
    users.insert_user(uid, username, users.hash_password(password), 'admin' if role == 'admin' else 'user')
    with db.user_db_ctx(uid):
        pass  # 立即创建该用户的独立数据库（建表 + 默认数据）
    return {'user': users.public_user(users.find_user_by_id(uid))}


@router.put('/users/{uid}')
def update_user(uid: str, payload: dict = Body(default={}), admin=Depends(get_admin)):
    target = users.find_user_by_id(uid)
    if not target:
        raise ApiError(404, '用户不存在')
    username = payload.get('username')
    password = payload.get('password')
    role = payload.get('role')
    disabled = payload.get('disabled')

    # 不能取消最后一个管理员的身份或将其禁用
    demoting_last_admin = (
        target['role'] == 'admin'
        and ((role is not None and role != 'admin') or bool(disabled))
        and users.admin_count() <= 1
    )
    if demoting_last_admin:
        raise ApiError(400, '不能禁用或降级系统中唯一的管理员')

    # 先完成全部校验，再写库
    if username is not None:
        if invalid_username(username):
            raise ApiError(400, '用户名需为 2-32 个字符且不含空白')
        clash = users.find_user_by_username(username)
        if clash and clash['id'] != target['id']:
            raise ApiError(400, '用户名已存在')
    if password is not None and (not isinstance(password, str) or len(password) < 6):
        raise ApiError(400, '密码至少需要 6 个字符')

    if username is not None:
        users.update_username(uid, username)
    if password is not None:
        users.update_password_hash(uid, users.hash_password(password))
    if role is not None:
        users.update_role(uid, 'admin' if role == 'admin' else 'user')
    if disabled is not None:
        users.update_disabled(uid, 1 if disabled else 0)
    if password is not None:
        users.revoke_all_sessions(uid)  # 重置密码后该用户所有会话下线
    return {'user': users.public_user(users.find_user_by_id(uid))}


@router.delete('/users/{uid}')
def delete_user(uid: str, admin=Depends(get_admin)):
    target = users.find_user_by_id(uid)
    if not target:
        raise ApiError(404, '用户不存在')
    if target['id'] == admin['id']:
        raise ApiError(400, '不能删除当前登录的账户')
    if target['role'] == 'admin' and users.admin_count() <= 1:
        raise ApiError(400, '不能删除系统中唯一的管理员')
    users.delete_user_row(uid)
    db.delete_user_db_file(uid)  # 同时删除该用户的独立数据文件（先释放缓存连接，Windows 文件锁）
    return {'ok': True}
