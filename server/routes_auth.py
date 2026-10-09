"""服务端认证路由（账户体系版；桌面端使用 desktop/local_auth.py 的本地单用户版，契约一致）

从原 routes_api.py 的认证部分原样迁移：login / logout / me / change-password + get_user_id 依赖。
"""
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

import users
from core.errors import ApiError

router = APIRouter(prefix='/api')

SESSION_COOKIE = users.SESSION_COOKIE
SESSION_MAX_AGE = users.SESSION_TTL


def get_user_id(request: Request) -> str:
    """除 login 与 holidays 外的所有业务端点都依赖本函数；校验链与旧 get_auth 完全一致"""
    token = request.cookies.get(SESSION_COOKIE)
    session = users.verify_session_token(token)
    if not session:
        raise ApiError(401, '未登录或会话已过期')
    user = users.find_user_by_id(session['uid'])
    if not user:
        raise ApiError(401, '账户不存在')
    if user['disabled']:
        raise ApiError(403, '账户已被禁用')
    # 已登出吊销的令牌 / 修改密码之前的旧令牌一律失效（iat 严格小于 sessions_since 才算旧）
    if users.is_session_revoked(token) or (user['sessions_since'] or 0) > session['iat']:
        raise ApiError(401, '会话已失效，请重新登录')
    return user['id']


def _set_session_cookie(resp, user_id):
    resp.set_cookie(
        SESSION_COOKIE, users.sign_session(user_id),
        path='/', httponly=True, samesite='lax', max_age=SESSION_MAX_AGE,
    )


@router.post('/auth/login')
def login(payload: dict = Body(default={})):
    user = users.find_user_by_username(payload.get('username'))
    if not user or not users.verify_password(payload.get('password'), user['password_hash']):
        raise ApiError(401, '用户名或密码错误')
    if user['disabled']:
        raise ApiError(403, '账户已被禁用，请联系管理员')
    resp = JSONResponse({'user': users.public_user(user)})
    _set_session_cookie(resp, user['id'])
    return resp


@router.post('/auth/logout')
def logout(request: Request):
    # 服务端吊销当前令牌（即使客户端保留 cookie 也无法继续使用）
    users.revoke_session(request.cookies.get(SESSION_COOKIE))
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax')
    return resp


@router.get('/auth/me')
def me(uid: str = Depends(get_user_id)):
    return {'user': users.public_user(users.find_user_by_id(uid))}


@router.post('/auth/change-password')
def change_password(payload: dict = Body(default={}), uid: str = Depends(get_user_id)):
    user = users.find_user_by_id(uid)
    if not users.verify_password(payload.get('oldPassword'), user['password_hash']):
        raise ApiError(400, '原密码错误')
    new_password = payload.get('newPassword')
    if not isinstance(new_password, str) or len(new_password) < 6:
        raise ApiError(400, '新密码至少需要 6 个字符')
    users.update_password_hash(user['id'], users.hash_password(new_password))
    users.revoke_all_sessions(user['id'])
    # 重新签发当前会话，避免改密后立刻被踢出
    resp = JSONResponse({'ok': True})
    _set_session_cookie(resp, user['id'])
    return resp
