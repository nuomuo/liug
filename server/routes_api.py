"""/api/* 业务路由（口径 1:1 对应原 Node 版 server/index.js）"""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

import db
import holidays
import users
from errors import ApiError
from import_csv import import_csv

router = APIRouter(prefix='/api')

SESSION_COOKIE = users.SESSION_COOKIE
SECRET = users.SECRET
SESSION_MAX_AGE = users.SESSION_TTL


def _beijing_now_iso():
    # 北京时间（UTC+8）本地时刻，毫秒精度（对齐 Node toISOString() 恒 3 位小数）
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]


# ---------- serialization（snake_case -> camelCase） ----------
def task_to_json(row):
    if row is None:
        return None
    return {
        'id': row['id'],
        'projectId': row['project_id'],
        'parentId': row['parent_id'],
        'title': row['title'],
        'content': row['content'],
        'isChecklist': bool(row['is_checklist']),
        'tags': [t for t in (row['tags'] or '').split(',') if t],
        'startDate': row['start_date'],
        'dueDate': row['due_date'],
        'priority': row['priority'],
        'status': row['status'],
        'sortOrder': row['sort_order'],
        'isAllDay': bool(row['is_all_day']),
        'isFloating': bool(row['is_floating']),
        'reminder': row['reminder'],
        'repeatFlag': row['repeat_flag'],
        'createdAt': row['created_at'],
        'completedAt': row['completed_at'],
    }


def project_to_json(row):
    if row is None:
        return None
    return {
        'id': row['id'],
        'name': row['name'],
        'color': row['color'],
        'emoji': row['emoji'],
        'kind': row['kind'],
        'folderId': row['folder_id'],
        'sortOrder': row['sort_order'],
    }


def folder_to_json(row):
    if row is None:
        return None
    return {'id': row['id'], 'name': row['name']}


def countdown_to_json(row):
    if row is None:
        return None
    return {
        'id': row['id'],
        'title': row['title'],
        'type': row['type'],
        'date': row['date'],
        'isLunar': bool(row['is_lunar']),
        'repeatYearly': bool(row['repeat_yearly']),
        'pinned': bool(row['pinned']),
        'sortOrder': row['sort_order'],
    }


# ---------- 鉴权依赖（对应 Express 的 /api 中间件） ----------
def get_auth(request: Request):
    """除 /api/auth/login 与 /api/holidays 外的所有 /api/* 都需要有效会话"""
    token = request.cookies.get(SESSION_COOKIE)
    session = users.verify_session_token(token, SECRET)
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
    return {'user': user, 'token': token}


def _set_session_cookie(resp, user_id):
    resp.set_cookie(
        SESSION_COOKIE, users.sign_session(user_id, SECRET),
        path='/', httponly=True, samesite='lax', max_age=SESSION_MAX_AGE,
    )


# ---------- 认证 ----------
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
    users.revoke_session(request.cookies.get(SESSION_COOKIE), SECRET)
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax')
    return resp


@router.get('/auth/me')
def me(auth: dict = Depends(get_auth)):
    return {'user': users.public_user(auth['user'])}


@router.post('/auth/change-password')
def change_password(payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    user = auth['user']
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


# ---------- 官方节假日（公共数据，无需登录） ----------
@router.get('/holidays')
async def holidays_endpoint(year: str = ''):
    try:
        y = int(year)
    except ValueError:
        y = datetime.now(timezone(timedelta(hours=8))).year  # 北京时间当前年
    if y < 2007 or y > 2100:
        raise ApiError(400, '年份需在 2007-2100 之间')
    try:
        return await holidays.get_holidays(y)
    except Exception as e:
        raise ApiError(502, '获取节假日数据失败：' + (str(e) or '未知错误'))


# ---------- bootstrap ----------
@router.get('/bootstrap')
def bootstrap(auth: dict = Depends(get_auth)):
    with db.user_db_ctx(auth['user']['id']) as conn:
        folders = [folder_to_json(r) for r in conn.execute('SELECT * FROM folders ORDER BY id').fetchall()]
        projects = [project_to_json(r) for r in conn.execute(
            'SELECT * FROM projects WHERE is_deleted = 0 ORDER BY sort_order, id').fetchall()]
        tasks = [task_to_json(r) for r in conn.execute(
            'SELECT * FROM tasks WHERE is_deleted = 0 AND parent_id IS NULL ORDER BY sort_order, id').fetchall()]
        subtasks = [task_to_json(r) for r in conn.execute(
            'SELECT * FROM tasks WHERE is_deleted = 0 AND parent_id IS NOT NULL ORDER BY sort_order, id').fetchall()]
        countdowns = [countdown_to_json(r) for r in conn.execute(
            'SELECT * FROM countdowns WHERE is_deleted = 0 ORDER BY pinned DESC, sort_order, id').fetchall()]
    return {'folders': folders, 'projects': projects, 'tasks': tasks, 'subtasks': subtasks, 'countdowns': countdowns}


# ---------- tasks ----------
@router.get('/tasks')
def list_tasks(auth: dict = Depends(get_auth)):
    with db.user_db_ctx(auth['user']['id']) as conn:
        rows = conn.execute('SELECT * FROM tasks WHERE is_deleted = 0 ORDER BY sort_order, id').fetchall()
    return [task_to_json(r) for r in rows]


TASK_FIELDS = {
    'projectId': 'project_id',
    'parentId': 'parent_id',
    'title': 'title',
    'content': 'content',
    'isChecklist': 'is_checklist',
    'tags': 'tags',
    'startDate': 'start_date',
    'dueDate': 'due_date',
    'priority': 'priority',
    'status': 'status',
    'sortOrder': 'sort_order',
    'isAllDay': 'is_all_day',
    'isFloating': 'is_floating',
    'reminder': 'reminder',
    'repeatFlag': 'repeat_flag',
    'completedAt': 'completed_at',
}


@router.post('/tasks')
def create_task(payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    b = payload

    def or_default(v, default):
        return default if v is None else v

    tags = b.get('tags')
    if isinstance(tags, list):
        tags = ','.join(str(t) for t in tags)
    elif tags is None:
        tags = ''
    with db.user_db_ctx(auth['user']['id']) as conn:
        min_order = conn.execute(
            'SELECT COALESCE(MIN(sort_order), 0) AS m FROM tasks WHERE is_deleted = 0'
        ).fetchone()['m']
        cur = conn.execute(
            'INSERT INTO tasks (project_id, parent_id, title, content, is_checklist, tags, start_date, due_date,'
            ' priority, status, sort_order, is_all_day, is_floating, reminder, repeat_flag, created_at, completed_at)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                or_default(b.get('projectId'), 1),
                b.get('parentId'),
                or_default(b.get('title'), ''),
                or_default(b.get('content'), ''),
                1 if b.get('isChecklist') else 0,
                tags,
                b.get('startDate'),
                b.get('dueDate'),
                or_default(b.get('priority'), 0),
                or_default(b.get('status'), 0),
                or_default(b.get('sortOrder'), min_order - 1),
                0 if b.get('isAllDay') is False else 1,  # 仅 JSON false 视为 0（对齐 === false）
                1 if b.get('isFloating') else 0,
                or_default(b.get('reminder'), ''),
                or_default(b.get('repeatFlag'), ''),
                _beijing_now_iso(),
                b.get('completedAt'),
            ),
        )
        row = conn.execute('SELECT * FROM tasks WHERE id = ?', (cur.lastrowid,)).fetchone()
    return task_to_json(row)


@router.put('/tasks/{task_id}')
def update_task(task_id: str, payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    id_ = int(task_id)  # 非数字 id 让异常自然抛出为 500（对齐 Node Number() 绑定语义）
    with db.user_db_ctx(auth['user']['id']) as conn:
        if not conn.execute('SELECT * FROM tasks WHERE id = ?', (id_,)).fetchone():
            raise ApiError(404, 'task not found')
        sets, params = [], {}
        for k, col in TASK_FIELDS.items():
            if k in payload:
                v = payload[k]
                if k == 'tags':
                    v = ','.join(str(t) for t in v) if isinstance(v, list) else v
                if k in ('isChecklist', 'isAllDay', 'isFloating'):
                    v = 1 if v else 0
                sets.append(f'{col} = :{k}')
                params[k] = v
        if sets:
            params['id'] = id_
            conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = :id", params)
        row = conn.execute('SELECT * FROM tasks WHERE id = ?', (id_,)).fetchone()
    return task_to_json(row)


@router.delete('/tasks/{task_id}')
def delete_task(task_id: str, auth: dict = Depends(get_auth)):
    id_ = int(task_id)
    with db.user_db_ctx(auth['user']['id']) as conn:
        # 软删除自身及其直接子任务（孙级不动，对齐 Node 版）
        conn.execute('UPDATE tasks SET is_deleted = 1 WHERE id = ? OR parent_id = ?', (id_, id_))
    return {'ok': True}


# ---------- projects ----------
@router.post('/projects')
def create_project(payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    b = payload
    with db.user_db_ctx(auth['user']['id']) as conn:
        max_order = conn.execute('SELECT COALESCE(MAX(sort_order), 0) AS m FROM projects').fetchone()['m']
        cur = conn.execute(
            'INSERT INTO projects (name, color, emoji, kind, folder_id, sort_order) VALUES (?,?,?,?,?,?)',
            (
                b.get('name') if b.get('name') is not None else '新清单',
                b.get('color') if b.get('color') is not None else '#484553',
                b.get('emoji') if b.get('emoji') is not None else '',
                b.get('kind') if b.get('kind') is not None else 'TASK',
                b.get('folderId'),
                max_order + 1,
            ),
        )
        row = conn.execute('SELECT * FROM projects WHERE id = ?', (cur.lastrowid,)).fetchone()
    return project_to_json(row)


@router.put('/projects/{project_id}')
def update_project(project_id: str, payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    id_ = int(project_id)
    b = payload
    with db.user_db_ctx(auth['user']['id']) as conn:
        sets, params = [], {'id': id_}
        for k, col in (('name', 'name'), ('color', 'color'), ('emoji', 'emoji'), ('folderId', 'folder_id')):
            if k in b:
                sets.append(f'{col} = :{k}')
                params[k] = b[k]
        if sets:
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = :id", params)
        # 无存在性检查：未命中时返回 null + 200（对齐 Node 行为）
        row = conn.execute('SELECT * FROM projects WHERE id = ?', (id_,)).fetchone()
    return project_to_json(row)


@router.delete('/projects/{project_id}')
def delete_project(project_id: str, auth: dict = Depends(get_auth)):
    id_ = int(project_id)
    if id_ == 1:
        raise ApiError(400, '收集箱不可删除')
    with db.user_db_ctx(auth['user']['id']) as conn:
        conn.execute('UPDATE projects SET is_deleted = 1 WHERE id = ?', (id_,))
        conn.execute('UPDATE tasks SET is_deleted = 1 WHERE project_id = ?', (id_,))
    return {'ok': True}


# ---------- search ----------
@router.get('/search')
def search(q: str = '', auth: dict = Depends(get_auth)):
    query = str(q or '').strip()
    if not query:
        return {'tasks': []}
    like = f"%{re.sub(r'[%_]', '', query)}%"
    with db.user_db_ctx(auth['user']['id']) as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE is_deleted = 0 AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)'
            ' ORDER BY due_date IS NULL, due_date LIMIT 200',
            (like, like, like),
        ).fetchall()
    return {'tasks': [task_to_json(r) for r in rows]}


# ---------- countdowns ----------
@router.post('/countdowns')
def create_countdown(payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    b = payload
    with db.user_db_ctx(auth['user']['id']) as conn:
        max_order = conn.execute('SELECT COALESCE(MAX(sort_order), 0) AS m FROM countdowns').fetchone()['m']
        cur = conn.execute(
            'INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, pinned, sort_order) VALUES (?,?,?,?,?,?,?)',
            (
                b['title'] if b.get('title') is not None else '纪念日',
                b['type'] if b.get('type') is not None else 'countdown',
                b['date'] if b.get('date') is not None else '',
                1 if b.get('isLunar') else 0,
                0 if b.get('repeatYearly') is False else 1,
                1 if b.get('pinned') else 0,
                max_order + 1,
            ),
        )
        row = conn.execute('SELECT * FROM countdowns WHERE id = ?', (cur.lastrowid,)).fetchone()
    return countdown_to_json(row)


@router.put('/countdowns/{cd_id}')
def update_countdown(cd_id: str, payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    id_ = int(cd_id)
    fields = {
        'title': 'title', 'type': 'type', 'date': 'date', 'isLunar': 'is_lunar',
        'repeatYearly': 'repeat_yearly', 'pinned': 'pinned', 'sortOrder': 'sort_order',
    }
    with db.user_db_ctx(auth['user']['id']) as conn:
        if not conn.execute('SELECT * FROM countdowns WHERE id = ?', (id_,)).fetchone():
            raise ApiError(404, 'countdown not found')
        sets, params = [], {'id': id_}
        for k, col in fields.items():
            if k in payload:
                v = payload[k]
                if k in ('isLunar', 'repeatYearly', 'pinned'):
                    v = 1 if v else 0
                sets.append(f'{col} = :{k}')
                params[k] = v
        if sets:
            conn.execute(f"UPDATE countdowns SET {', '.join(sets)} WHERE id = :id", params)
        row = conn.execute('SELECT * FROM countdowns WHERE id = ?', (id_,)).fetchone()
    return countdown_to_json(row)


@router.delete('/countdowns/{cd_id}')
def delete_countdown(cd_id: str, auth: dict = Depends(get_auth)):
    id_ = int(cd_id)
    with db.user_db_ctx(auth['user']['id']) as conn:
        conn.execute('UPDATE countdowns SET is_deleted = 1 WHERE id = ?', (id_,))
    return {'ok': True}


# ---------- import ----------
@router.post('/import')
def import_endpoint(payload: dict = Body(default={}), auth: dict = Depends(get_auth)):
    csv_path = payload.get('csvPath')
    if not csv_path:
        raise ApiError(400, 'csvPath required')
    try:
        with db.user_db_ctx(auth['user']['id']) as conn:
            return import_csv(conn, csv_path)
    except ApiError:
        raise
    except Exception as e:
        raise ApiError(500, str(e) or '导入失败')


# ---------- reset ----------
@router.post('/reset')
def reset(auth: dict = Depends(get_auth)):
    # 重置当前用户自己的数据（不影响其他用户）；countdowns 不重置，对齐 Node 版
    with db.user_db_ctx(auth['user']['id']) as conn:
        for table in ('tasks', 'projects', 'folders'):
            conn.execute(f'DELETE FROM {table}')
        db.ensure_default_data(conn)
    return {'ok': True}
