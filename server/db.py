"""每用户独立 SQLite 数据库（口径 1:1 对应原 Node 版 server/db.js）

- 用户数据目录：DIDA_USERS_DIR 环境变量或 data/users/（测试指向 data/users-test）
- 每个用户一个 <uuid>.db 文件；连接缓存 + 每用户 RLock（FastAPI 同步端点跑线程池，同用户请求按锁串行）
- 连接统一：autocommit（对齐 node:sqlite 逐语句提交）+ WAL + 外键开启（对齐 node:sqlite 默认）
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'

# 用户数据目录：每个用户一个独立 SQLite 文件（文件名 = 用户唯一 ID）；
# 测试通过 DIDA_USERS_DIR 指向独立目录，避免污染正式用户数据
USERS_DIR = Path(os.environ.get('DIDA_USERS_DIR') or (DATA_DIR / 'users')).resolve()
USERS_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
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


def user_db_path(user_id):
    return USERS_DIR / f'{user_id}.db'


def open_database_at_path(db_path):
    """打开并初始化任意路径的数据库（建表 + WAL）；不写入默认数据（CLI 导入口径与 Node 一致）"""
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    # 注意：与 Node 版一致，不启用 foreign_keys 强制（Node 仅开 WAL）。
    # 建表语句中的 FK 声明在 Node 下同样不生效，级联删除由业务代码手动完成；
    # 强制 FK 会导致合法请求（如缺省 projectId=1 的悬空引用）500，行为与原版分歧。
    conn.executescript(SCHEMA)
    return conn


# 已打开的用户库连接缓存：user_id -> (conn, RLock)，对应 Node 版的 openConnections Map
_open = {}
_open_guard = threading.Lock()


def user_db_ctx(user_id):
    """获取（或首次打开并初始化）指定用户的独立数据库，返回在其锁内执行的上下文管理器"""
    with _open_guard:
        entry = _open.get(user_id)
        if entry is None:
            conn = open_database_at_path(user_db_path(user_id))
            ensure_default_data(conn)
            entry = (conn, threading.RLock())
            _open[user_id] = entry
    conn, lock = entry

    @contextmanager
    def _ctx():
        with lock:
            yield conn

    return _ctx()


def close_user_db(user_id):
    """关闭某个用户的连接（用于删除用户前释放文件句柄，Windows 下必须）"""
    with _open_guard:
        entry = _open.pop(user_id, None)
    if entry:
        try:
            entry[0].close()
        except sqlite3.Error:
            pass


def delete_user_db_file(user_id):
    """删除某个用户的数据库文件（含 WAL/SHM 附属文件）；先释放缓存连接"""
    close_user_db(user_id)
    for suffix in ('', '-wal', '-shm'):
        p = Path(str(user_db_path(user_id)) + suffix)
        if p.exists():
            p.unlink()


DEFAULT_PROJECTS = [
    ('收集箱', '#4096ff', '', 'TASK', 0),
    ('生活', '#484553', '🍎', 'TASK', 1),
    ('工作任务清单', '#ff6161', '💼', 'TASK', 2),
]

# 预置节日（与原版一致的农历节日 + 公历节日；农历条目的 date 存农历月-日，年份忽略）
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


def ensure_default_data(conn):
    n = conn.execute('SELECT COUNT(*) AS n FROM projects WHERE is_deleted = 0').fetchone()['n']
    if n == 0:
        conn.executemany(
            'INSERT INTO projects (name, color, emoji, kind, sort_order) VALUES (?,?,?,?,?)',
            DEFAULT_PROJECTS,
        )
    _seed_countdowns(conn)


def _seed_countdowns(conn):
    n = conn.execute('SELECT COUNT(*) AS n FROM countdowns WHERE is_deleted = 0').fetchone()['n']
    if n > 0:
        return
    conn.executemany(
        'INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, sort_order) VALUES (?,?,?,?,?,?)',
        [(title, type_, date, is_lunar, 1, i) for i, (title, type_, date, is_lunar) in enumerate(DEFAULT_COUNTDOWNS)],
    )
