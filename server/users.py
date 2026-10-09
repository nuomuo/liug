"""用户主库（账户/密码/角色）+ 会话机制（仅服务端持有；桌面 exe 不打包本模块）

- 密码 scrypt、会话 HMAC 令牌等纯函数复用 core/auth.py
- 会话密钥：主应用复用 <用户主库>.secret（沿用旧 Node 后端密钥文件，已有登录态迁移后不失效）
- 首次启动 bootstrap：默认 admin/admin123 + 旧单用户库只读迁移（VACUUM INTO，不改原文件）
"""
import os
import sqlite3
import time
import uuid
from pathlib import Path

from core import db
from core.auth import (
    SESSION_TTL,
    hash_password,
    sign_session as _sign_session,
    token_sig,
    verify_password,
    verify_session_token as _verify_token,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'

# 用户主库：默认 data/users.db；测试通过 LIUG_USERS_DB_PATH 指向独立文件
USERS_DB_PATH = Path(os.environ.get('LIUG_USERS_DB_PATH') or (DATA_DIR / 'users.db')).resolve()

SESSION_COOKIE = 'liug_session'
SESSION_TTL = SESSION_TTL


def _connect():
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def init_users_db():
    """首次启动（或指向全新测试库）时确保表结构存在，口径与 server/users.js 一致"""
    conn = _connect()
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
            pass  # 列已存在（兼容旧库）
        conn.commit()
    finally:
        conn.close()


# ---------- 会话令牌（密钥 = users.db.secret，格式与桌面本地端 / 旧 Node 版一致） ----------
def _load_secret(suffix):
    p = Path(str(USERS_DB_PATH) + suffix)
    if p.exists():
        return p.read_text(encoding='utf-8').strip()
    s = secrets_hex()
    p.write_text(s, encoding='utf-8')
    return s


def secrets_hex():
    import secrets as _s
    return _s.token_hex(32)


# 主应用会话密钥：与旧 Node 后端共用同一文件（users.db.secret），保证已有登录态不失效
SECRET = _load_secret('.secret')


def sign_session(user_id):
    return _sign_session(user_id, SECRET)


def verify_session_token(token):
    return _verify_token(token, SECRET)


# ---------- 会话吊销 ----------
def revoke_session(token):
    """登出：吊销单个令牌（令牌本身带有效期，过期条目自动清理）"""
    session = verify_session_token(token)
    if not session:
        return
    conn = _connect()
    try:
        conn.execute('INSERT OR IGNORE INTO revoked_sessions (sig, exp) VALUES (?,?)', (token_sig(token), session['exp']))
        conn.execute('DELETE FROM revoked_sessions WHERE exp < ?', (int(time.time() * 1000),))
        conn.commit()
    finally:
        conn.close()


def is_session_revoked(token):
    if not token:
        return False
    sig = token_sig(token)
    if not sig:
        return False
    conn = _connect()
    try:
        return bool(conn.execute('SELECT 1 FROM revoked_sessions WHERE sig = ?', (sig,)).fetchone())
    finally:
        conn.close()


def revoke_all_sessions(user_id):
    """修改密码等场景：使某用户的所有既有会话立即失效（iat 严格小于 sessions_since 的令牌作废）"""
    conn = _connect()
    try:
        conn.execute('UPDATE users SET sessions_since = ? WHERE id = ?', (int(time.time() * 1000), user_id))
        conn.commit()
    finally:
        conn.close()


# ---------- 用户查询与写入 ----------
def find_user_by_username(username):
    conn = _connect()
    try:
        return conn.execute('SELECT * FROM users WHERE username = ?', (str(username or ''),)).fetchone()
    finally:
        conn.close()


def find_user_by_id(uid):
    conn = _connect()
    try:
        return conn.execute('SELECT * FROM users WHERE id = ?', (str(uid or ''),)).fetchone()
    finally:
        conn.close()


def admin_count():
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND disabled = 0").fetchone()['n']
    finally:
        conn.close()


def list_users():
    conn = _connect()
    try:
        return conn.execute(
            'SELECT id, username, role, disabled, created_at FROM users ORDER BY created_at, username'
        ).fetchall()
    finally:
        conn.close()


def insert_user(uid, username, password_hash, role):
    conn = _connect()
    try:
        conn.execute(
            'INSERT INTO users (id, username, password_hash, role) VALUES (?,?,?,?)',
            (uid, username, password_hash, 'admin' if role == 'admin' else 'user'),
        )
        conn.commit()
    finally:
        conn.close()


def update_password_hash(uid, password_hash):
    conn = _connect()
    try:
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, uid))
        conn.commit()
    finally:
        conn.close()


def update_username(uid, username):
    conn = _connect()
    try:
        conn.execute('UPDATE users SET username = ? WHERE id = ?', (username, uid))
        conn.commit()
    finally:
        conn.close()


def update_role(uid, role):
    conn = _connect()
    try:
        conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, uid))
        conn.commit()
    finally:
        conn.close()


def update_disabled(uid, disabled):
    conn = _connect()
    try:
        conn.execute('UPDATE users SET disabled = ? WHERE id = ?', (1 if disabled else 0, uid))
        conn.commit()
    finally:
        conn.close()


def delete_user_row(uid):
    conn = _connect()
    try:
        conn.execute('DELETE FROM users WHERE id = ?', (uid,))
        conn.commit()
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


# ---------- 首次启动：默认管理员 + 旧单库数据迁移 ----------
def bootstrap_users(legacy_db_path=None):
    init_users_db()
    conn = _connect()
    try:
        n = conn.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n']
    finally:
        conn.close()
    if n > 0:
        return

    uid = str(uuid.uuid4())
    insert_user(uid, 'admin', hash_password('admin123'), 'admin')
    admin = find_user_by_id(uid)

    # 生产环境（未重定向用户主库）且存在旧正式库时，把旧数据只读复制为 admin 的用户库。
    # 仅读取 schedule.db（VACUUM INTO），不修改、不删除原文件。
    if not os.environ.get('LIUG_USERS_DB_PATH') and legacy_db_path and Path(legacy_db_path).exists():
        try:
            dest = db.user_db_path(admin['id'])
            src = sqlite3.connect(Path(legacy_db_path).resolve().as_uri() + '?mode=ro', uri=True)
            try:
                src.execute(f"VACUUM INTO '{str(dest).replace(chr(39), chr(39) * 2)}'")
            finally:
                src.close()
            print('[users] 已将原有 schedule.db 数据迁移为 admin 账户的独立数据库')
        except Exception as e:
            print(f'[users] 旧数据迁移失败（将使用全新的 admin 数据库）: {e}')
    print('[users] 已创建默认管理员账户：admin / admin123（请尽快修改密码）')
