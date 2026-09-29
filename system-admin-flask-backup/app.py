"""系统管理独立程序（用户管理）— Flask 后端

前后端分离：本程序只提供 /system/* JSON API，前端为 web/ 目录下的纯静态文件，不做模板渲染。
与主程序共享同一个用户主库（默认 data/users.db；测试请用 DIDA_USERS_DB_PATH / DIDA_USERS_DIR 重定向到测试库）。

启动：python app.py（生产端口 4302）
测试：DIDA_USERS_DB_PATH=data/users.test.db DIDA_USERS_DIR=data/users-test PORT=4303 python app.py
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'

# 用户主库 / 用户数据目录：与 Node 主程序同一套约定（可重定向到测试库）
USERS_DB_PATH = Path(os.environ.get('DIDA_USERS_DB_PATH') or (DATA_DIR / 'users.db')).resolve()
USERS_DIR = Path(os.environ.get('DIDA_USERS_DIR') or (DATA_DIR / 'users')).resolve()
PORT = int(os.environ.get('PORT', '4302'))

SESSION_COOKIE = 'dida_system_session'
SESSION_TTL = 7 * 24 * 3600  # 7 天
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 16384, 8, 1, 64  # 与 Node crypto.scryptSync 默认参数一致

app = Flask(__name__, static_folder=None)


# ---------- 数据库 ----------
def db():
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def init_users_db():
    """首次启动（或指向全新测试库）时确保表结构存在，口径与 server/users.js 一致"""
    conn = db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              disabled INTEGER NOT NULL DEFAULT 0,
              sessions_since INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS revoked_sessions (
              sig TEXT PRIMARY KEY,
              exp INTEGER NOT NULL
            );
            """
        )
        try:
            conn.execute('ALTER TABLE users ADD COLUMN sessions_since INTEGER NOT NULL DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.commit()
    finally:
        conn.close()


def find_user_by_username(username):
    conn = db()
    try:
        return conn.execute('SELECT * FROM users WHERE username = ?', (str(username or ''),)).fetchone()
    finally:
        conn.close()


def find_user_by_id(uid):
    conn = db()
    try:
        return conn.execute('SELECT * FROM users WHERE id = ?', (str(uid or ''),)).fetchone()
    finally:
        conn.close()


def admin_count():
    conn = db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND disabled = 0"
        ).fetchone()['n']
    finally:
        conn.close()


def public_user(u):
    if not u:
        return None
    return {
        'id': u['id'],
        'username': u['username'],
        'role': u['role'],
        'disabled': bool(u['disabled']),
        'createdAt': u['created_at'],
    }


# ---------- 密码哈希（与 Node scrypt$salt$hash 格式互通） ----------
def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        str(password).encode('utf-8'),
        salt=salt.encode('utf-8'),
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    ).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, stored):
    try:
        scheme, salt, digest = str(stored or '').split('$')
        if scheme != 'scrypt' or not salt or not digest:
            return False
        test = hashlib.scrypt(
            str(password).encode('utf-8'),
            salt=salt.encode('utf-8'),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
            maxmem=64 * 1024 * 1024,
        ).hex()
        return hmac.compare_digest(test, digest)
    except Exception:
        return False


# ---------- 会话（HMAC 签名 Cookie，独立于主程序的密钥） ----------
SECRET_PATH = Path(str(USERS_DB_PATH) + '.system-secret')
if SECRET_PATH.exists():
    SECRET = SECRET_PATH.read_text(encoding='utf-8').strip()
else:
    SECRET = secrets.token_hex(32)
    SECRET_PATH.write_text(SECRET, encoding='utf-8')


def sign_session(user_id):
    now = int(time.time() * 1000)
    payload = base64url(json.dumps({'uid': user_id, 'iat': now, 'exp': now + SESSION_TTL * 1000}))
    sig = base64url(hmac.new(SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    return f'{payload}.{sig}'


def verify_session_token(token):
    if not token or not isinstance(token, str) or '.' not in token:
        return None
    payload, sig = token.rsplit('.', 1)
    expect = base64url(hmac.new(SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(base64url_decode(payload))
        if not data.get('uid') or data.get('exp', 0) < time.time() * 1000:
            return None
        return data
    except Exception:
        return None


def base64url(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def base64url_decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def revoke_session(token):
    session = verify_session_token(token)
    if not session:
        return
    sig = token.rsplit('.', 1)[1]
    conn = db()
    try:
        conn.execute('INSERT OR IGNORE INTO revoked_sessions (sig, exp) VALUES (?,?)', (sig, session['exp']))
        conn.execute('DELETE FROM revoked_sessions WHERE exp < ?', (int(time.time() * 1000),))
        conn.commit()
    finally:
        conn.close()


def revoke_all_sessions(user_id):
    """修改密码后使该用户所有既有会话失效（主程序与自程序共用此口径）"""
    conn = db()
    try:
        conn.execute('UPDATE users SET sessions_since = ? WHERE id = ?', (int(time.time() * 1000), user_id))
        conn.commit()
    finally:
        conn.close()


def current_user():
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    conn = db()
    try:
        session = verify_session_token(token)
        if not session:
            return None
        sig = token.rsplit('.', 1)[1]
        if conn.execute('SELECT 1 FROM revoked_sessions WHERE sig = ?', (sig,)).fetchone():
            return None
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['uid'],)).fetchone()
        if not user or user['disabled']:
            return None
        if (user['sessions_since'] or 0) > session['iat']:
            return None  # 密码已被重置，旧会话失效
        return user
    finally:
        conn.close()


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({'error': '未登录或会话已过期'}), 401
        if user['role'] != 'admin':
            return jsonify({'error': '需要管理员权限'}), 403
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


# ---------- 每用户独立数据库（建表 + 默认数据，口径与 server/db.js 一致） ----------
USER_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#484553',
  emoji TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'TASK',
  folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  is_checklist INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL DEFAULT '',
  start_date TEXT,
  due_date TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  status INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_all_day INTEGER NOT NULL DEFAULT 1,
  is_floating INTEGER NOT NULL DEFAULT 0,
  reminder TEXT NOT NULL DEFAULT '',
  repeat_flag TEXT NOT NULL DEFAULT '',
  progress INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at TEXT,
  is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
CREATE TABLE IF NOT EXISTS countdowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'countdown',
  date TEXT NOT NULL,
  is_lunar INTEGER NOT NULL DEFAULT 0,
  repeat_yearly INTEGER NOT NULL DEFAULT 1,
  pinned INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_deleted INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_PROJECTS = [
    ('收集箱', '#4096ff', '', 'TASK', 0),
    ('生活', '#484553', '🍎', 'TASK', 1),
    ('工作任务清单', '#ff6161', '💼', 'TASK', 2),
]

DEFAULT_COUNTDOWNS = [
    ('元旦', 'festival', '2026-01-01', 0),
    ('除夕', 'festival', '2000-12-30', 1),
    ('春节', 'festival', '2000-01-01', 1),
    ('元宵节', 'festival', '2000-01-15', 1),
    ('端午节', 'festival', '2000-05-05', 1),
    ('中秋节', 'festival', '2000-08-15', 1),
    ('国庆节', 'festival', '2026-10-01', 0),
    ('圣诞节', 'festival', '2026-12-25', 0),
]


def user_db_path(user_id):
    return USERS_DIR / f'{user_id}.db'


def init_user_db(user_id):
    """新建用户时立即创建其独立数据库（建表 + 默认数据）"""
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(user_db_path(user_id))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(USER_DB_SCHEMA)
        if conn.execute('SELECT COUNT(*) AS n FROM projects WHERE is_deleted = 0').fetchone()['n'] == 0:
            conn.executemany(
                'INSERT INTO projects (name, color, emoji, kind, sort_order) VALUES (?,?,?,?,?)',
                DEFAULT_PROJECTS,
            )
        if conn.execute('SELECT COUNT(*) AS n FROM countdowns WHERE is_deleted = 0').fetchone()['n'] == 0:
            conn.executemany(
                'INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, sort_order) VALUES (?,?,?,?,?,?)',
                [(t, ty, d, lu, 1, i) for i, (t, ty, d, lu) in enumerate(DEFAULT_COUNTDOWNS)],
            )
        conn.commit()
    finally:
        conn.close()


def delete_user_db_files(user_id):
    for suffix in ('', '-wal', '-shm'):
        p = Path(str(user_db_path(user_id)) + suffix)
        if p.exists():
            p.unlink()


# ---------- 校验 ----------
USERNAME_RE = re.compile(r'^\S{2,32}$')


def invalid_username(username):
    return not isinstance(username, str) or not USERNAME_RE.match(username)


# ---------- 认证接口 ----------
@app.post('/system/auth/login')
def login():
    data = request.get_json(silent=True) or {}
    user = find_user_by_username(data.get('username'))
    if not user or not verify_password(data.get('password', ''), user['password_hash']):
        return jsonify({'error': '用户名或密码错误'}), 401
    if user['disabled']:
        return jsonify({'error': '账户已被禁用'}), 403
    if user['role'] != 'admin':
        return jsonify({'error': '需要管理员权限'}), 403
    token = sign_session(user['id'])
    resp = jsonify({'user': public_user(user)})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite='Lax', max_age=SESSION_TTL, path='/')
    return resp


@app.post('/system/auth/logout')
def logout():
    revoke_session(request.cookies.get(SESSION_COOKIE))
    resp = jsonify({'ok': True})
    resp.delete_cookie(SESSION_COOKIE, path='/')
    return resp


@app.get('/system/auth/me')
@require_admin
def me():
    return jsonify({'user': public_user(g.user)})


# ---------- 用户管理接口（仅管理员） ----------
@app.get('/system/users')
@require_admin
def list_users():
    conn = db()
    try:
        rows = conn.execute(
            'SELECT id, username, role, disabled, created_at FROM users ORDER BY created_at, username'
        ).fetchall()
        return jsonify({'users': [public_user(r) for r in rows]})
    finally:
        conn.close()


@app.post('/system/users')
@require_admin
def create_user():
    data = request.get_json(silent=True) or {}
    username, password, role = data.get('username'), data.get('password'), data.get('role')
    if invalid_username(username):
        return jsonify({'error': '用户名需为 2-32 个字符且不含空白'}), 400
    if not isinstance(password, str) or len(password) < 6:
        return jsonify({'error': '密码至少需要 6 个字符'}), 400
    if find_user_by_username(username):
        return jsonify({'error': '用户名已存在'}), 400
    uid = str(uuid.uuid4())
    conn = db()
    try:
        conn.execute(
            'INSERT INTO users (id, username, password_hash, role) VALUES (?,?,?,?)',
            (uid, username, hash_password(password), 'admin' if role == 'admin' else 'user'),
        )
        conn.commit()
    finally:
        conn.close()
    init_user_db(uid)  # 立即创建该用户的独立数据库
    return jsonify({'user': public_user(find_user_by_id(uid))})


@app.put('/system/users/<uid>')
@require_admin
def update_user(uid):
    target = find_user_by_id(uid)
    if not target:
        return jsonify({'error': '用户不存在'}), 404
    data = request.get_json(silent=True) or {}
    username, password, role, disabled = data.get('username'), data.get('password'), data.get('role'), data.get('disabled')

    # 不能取消最后一个管理员的身份或将其禁用
    demoting_last_admin = (
        target['role'] == 'admin'
        and ((role is not None and role != 'admin') or bool(disabled))
        and admin_count() <= 1
    )
    if demoting_last_admin:
        return jsonify({'error': '不能禁用或降级系统中唯一的管理员'}), 400

    # 先完成全部校验，再写库
    if username is not None:
        if invalid_username(username):
            return jsonify({'error': '用户名需为 2-32 个字符且不含空白'}), 400
        clash = find_user_by_username(username)
        if clash and clash['id'] != target['id']:
            return jsonify({'error': '用户名已存在'}), 400
    if password is not None and (not isinstance(password, str) or len(password) < 6):
        return jsonify({'error': '密码至少需要 6 个字符'}), 400

    conn = db()
    try:
        if username is not None:
            conn.execute('UPDATE users SET username = ? WHERE id = ?', (username, uid))
        if password is not None:
            conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hash_password(password), uid))
        if role is not None:
            conn.execute('UPDATE users SET role = ? WHERE id = ?', ('admin' if role == 'admin' else 'user', uid))
        if disabled is not None:
            conn.execute('UPDATE users SET disabled = ? WHERE id = ?', (1 if disabled else 0, uid))
        conn.commit()
    finally:
        conn.close()
    if password is not None:
        revoke_all_sessions(uid)  # 重置密码后该用户所有会话下线
    return jsonify({'user': public_user(find_user_by_id(uid))})


@app.delete('/system/users/<uid>')
@require_admin
def delete_user(uid):
    target = find_user_by_id(uid)
    if not target:
        return jsonify({'error': '用户不存在'}), 404
    if target['id'] == g.user['id']:
        return jsonify({'error': '不能删除当前登录的账户'}), 400
    if target['role'] == 'admin' and admin_count() <= 1:
        return jsonify({'error': '不能删除系统中唯一的管理员'}), 400
    conn = db()
    try:
        conn.execute('DELETE FROM users WHERE id = ?', (uid,))
        conn.commit()
    finally:
        conn.close()
    delete_user_db_files(uid)  # 同时删除该用户的独立数据文件
    return jsonify({'ok': True})


# ---------- 静态前端（前后端分离：仅托管 web/ 静态文件，无模板渲染） ----------
@app.get('/')
def index():
    return send_from_directory(BASE_DIR / 'web', 'index.html')


@app.get('/<path:filename>')
def static_files(filename):
    return send_from_directory(BASE_DIR / 'web', filename)


if __name__ == '__main__':
    init_users_db()
    print(f'[system-admin] 用户管理程序已启动：http://localhost:{PORT}（用户主库：{USERS_DB_PATH}）')
    app.run(host='0.0.0.0', port=PORT)
