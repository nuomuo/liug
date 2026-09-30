"""用户主库（账户/密码/角色）+ 会话机制（口径 1:1 对应原 Node 版 server/users.js）

- 密码：scrypt$<hex盐>$<hex哈希>，与 Node crypto.scryptSync 互通（盐为 hex 字符串直接作 bytes）
- 会话：HMAC-SHA256 签名的 base64url 无状态令牌 + revoked_sessions 吊销表 + sessions_since 批量失效
- 会话密钥：主应用复用 <用户主库>.secret（沿用旧 Node 后端密钥文件，已有登录态迁移后不失效）
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

import db

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'

# 用户主库：默认 data/users.db；测试通过 LIUG_USERS_DB_PATH 指向独立文件
USERS_DB_PATH = Path(os.environ.get('LIUG_USERS_DB_PATH') or (DATA_DIR / 'users.db')).resolve()

SESSION_COOKIE = 'liug_session'
SESSION_TTL = 7 * 24 * 3600  # 7 天（秒）
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 16384, 8, 1, 64  # 与 Node crypto.scryptSync 默认参数一致


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


# ---------- 会话令牌（HMAC 签名 Cookie，格式与 Node 版互通） ----------
def _load_secret(suffix):
    p = Path(str(USERS_DB_PATH) + suffix)
    if p.exists():
        return p.read_text(encoding='utf-8').strip()
    s = secrets.token_hex(32)
    p.write_text(s, encoding='utf-8')
    return s


# 主应用会话密钥：与旧 Node 后端共用同一文件（users.db.secret），保证已有登录态不失效
SECRET = _load_secret('.secret')


def _base64url(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _base64url_decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign_session(user_id, secret=SECRET):
    now = int(time.time() * 1000)
    payload = _base64url(json.dumps({'uid': user_id, 'iat': now, 'exp': now + SESSION_TTL * 1000}))
    sig = _base64url(hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    return f'{payload}.{sig}'


def verify_session_token(token, secret=SECRET):
    """校验令牌签名与有效期，返回 {uid, iat, exp} 或 None"""
    if not token or not isinstance(token, str) or '.' not in token:
        return None
    payload, sig = token.rsplit('.', 1)
    expect = _base64url(hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(_base64url_decode(payload))
        if not data.get('uid') or not data.get('exp') or data['exp'] < int(time.time() * 1000):
            return None
        return data
    except Exception:
        return None


# ---------- 会话吊销 ----------
def revoke_session(token, secret=SECRET):
    """登出：吊销单个令牌（令牌本身带有效期，过期条目自动清理）"""
    session = verify_session_token(token, secret)
    if not session:
        return
    sig = token.rsplit('.', 1)[1]
    conn = _connect()
    try:
        conn.execute('INSERT OR IGNORE INTO revoked_sessions (sig, exp) VALUES (?,?)', (sig, session['exp']))
        conn.execute('DELETE FROM revoked_sessions WHERE exp < ?', (int(time.time() * 1000),))
        conn.commit()
    finally:
        conn.close()


def is_session_revoked(token):
    if not token:
        return False
    sig = token.rsplit('.', 1)[1]
    conn = _connect()
    try:
        return bool(conn.execute('SELECT 1 FROM revoked_sessions WHERE sig = ?', (sig,)).fetchone())
    finally:
        conn.close()


def revoke_all_sessions(user_id):
    """修改密码等场景：使某用户的所有既有会话立即失效（ia严格小于 sessions_since 的令牌作废）"""
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
