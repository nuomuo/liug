"""每用户独立 SQLite 数据库（本地端与远程端共用的数据层）

- 用户数据目录：首次访问时读 LIUG_USERS_DIR 环境变量（惰性解析，便于启动器在导入后设置），
  缺省为 <项目根>/data/users/；测试指向独立目录，避免污染正式用户数据
- 每个用户一个 <uid>.db 文件；连接缓存 + 每用户 RLock（FastAPI 同步端点跑线程池，同用户请求按锁串行）
- 连接统一：autocommit（对齐 node:sqlite 逐语句提交）+ WAL
- 同步支持：每表自动维护 guid（跨库身份）/ updated_at（LWW 时间戳，触发器触碰），
  硬删除留 _sync_tombstones 墓碑；业务代码无需关心（详见 core/sync.py）
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / 'data'

# 惰性解析：桌面启动器/测试可在导入 core 之后的任意时刻（首次 DB 访问前）设置 LIUG_USERS_DIR
_USERS_DIR_CACHE = None


def users_dir() -> Path:
    global _USERS_DIR_CACHE
    if _USERS_DIR_CACHE is None:
        d = os.environ.get('LIUG_USERS_DIR')
        _USERS_DIR_CACHE = Path(d).resolve() if d else (DATA_DIR / 'users')
        _USERS_DIR_CACHE.mkdir(parents=True, exist_ok=True)
    return _USERS_DIR_CACHE


SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  guid TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#484553',
  emoji TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'TASK',
  folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  guid TEXT,
  updated_at TEXT
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
  is_deleted INTEGER NOT NULL DEFAULT 0,
  guid TEXT,
  updated_at TEXT
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
  is_deleted INTEGER NOT NULL DEFAULT 0,
  guid TEXT,
  updated_at TEXT
);

-- 硬删除墓碑（软删除走行内 is_deleted；reset / CSV 导入的硬 DELETE 由触发器在此留痕，
-- 同步时据此把删除传播到对端）
CREATE TABLE IF NOT EXISTS _sync_tombstones (
  table_name TEXT NOT NULL,
  guid TEXT NOT NULL,
  deleted_at TEXT NOT NULL,
  PRIMARY KEY (table_name, guid)
);
"""

# ---------- 同步支持列（guid / updated_at / 墓碑） ----------
# 每张业务表参与「变更检测」的数据列（触发器比较新旧值用；不含 id/guid/updated_at）
SYNC_TABLES = {
    'folders': ['name'],
    'projects': ['name', 'color', 'emoji', 'kind', 'folder_id', 'sort_order', 'is_deleted'],
    'tasks': [
        'project_id', 'parent_id', 'title', 'content', 'is_checklist', 'tags', 'start_date',
        'due_date', 'priority', 'status', 'sort_order', 'is_all_day', 'is_floating',
        'reminder', 'repeat_flag', 'progress', 'created_at', 'completed_at', 'is_deleted',
    ],
    'countdowns': ['title', 'type', 'date', 'is_lunar', 'repeat_yearly', 'pinned', 'sort_order', 'is_deleted'],
}

# 北京时间毫秒精度 ISO（与 core/routes._beijing_now_iso 同口径，字符串比较即时间序）
NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%S','now','+8 hours') || '.' || substr(strftime('%f','now','+8 hours'),4,3)"


def _triggers_sql() -> str:
    """生成四张业务表的同步触发器（INSERT 补全 / UPDATE 触碰 / DELETE 墓碑）

    - ins：业务 INSERT 不写 guid/updated_at 时自动补全（同步写入两者都显式给值，不触发）
    - touch：数据列有实际变化且本次 UPDATE 未显式修改 updated_at 时触碰时间戳
      （同步 apply 的 UPDATE 总是显式带更新的 updated_at，不会被覆盖）
    - del：硬删除时留墓碑，供同步传播（幂等 REPLACE）
    """
    parts = []
    for t, cols in SYNC_TABLES.items():
        changed_expr = ' OR '.join(f'NEW.{c} IS NOT OLD.{c}' for c in cols)
        # DROP 后重建（而非 IF NOT EXISTS）：触发器定义更新后老库自动生效新逻辑
        parts.append(f"""
DROP TRIGGER IF EXISTS trg_{t}_ins;
CREATE TRIGGER trg_{t}_ins AFTER INSERT ON {t}
WHEN NEW.guid IS NULL OR NEW.updated_at IS NULL
BEGIN
  UPDATE {t} SET
    guid = COALESCE(NEW.guid, lower(hex(randomblob(16)))),
    updated_at = COALESCE(NEW.updated_at, {NOW_SQL})
  WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_{t}_touch;
CREATE TRIGGER trg_{t}_touch AFTER UPDATE ON {t}
WHEN NEW.updated_at = OLD.updated_at AND ({changed_expr})
BEGIN
  UPDATE {t} SET updated_at = {NOW_SQL} WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_{t}_del;
CREATE TRIGGER trg_{t}_del AFTER DELETE ON {t}
WHEN OLD.guid IS NOT NULL
BEGIN
  INSERT OR REPLACE INTO _sync_tombstones (table_name, guid, deleted_at)
  VALUES ('{t}', OLD.guid, {NOW_SQL});
END;
""")
    return '\n'.join(parts)


def _migrate_sync_columns(conn):
    """老库迁移：补 guid / updated_at 列并回填（新库建表已含，仅补索引）"""
    for t in SYNC_TABLES:
        cols = {r['name'] for r in conn.execute(f'PRAGMA table_info({t})')}
        if not cols:
            continue  # 表不存在（异常库）交给上层报错
        if 'guid' not in cols:
            conn.execute(f'ALTER TABLE {t} ADD COLUMN guid TEXT')
            conn.execute(f'UPDATE {t} SET guid = lower(hex(randomblob(16))) WHERE guid IS NULL')
        if 'updated_at' not in cols:
            conn.execute(f'ALTER TABLE {t} ADD COLUMN updated_at TEXT')
            conn.execute(f'UPDATE {t} SET updated_at = {NOW_SQL} WHERE updated_at IS NULL')
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{t}_guid ON {t}(guid)')


def user_db_path(user_id):
    return users_dir() / f'{user_id}.db'


def open_database_at_path(db_path):
    """打开并初始化任意路径的数据库（建表 + 同步迁移 + WAL）；不写入默认数据（CLI 导入口径与 Node 一致）"""
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    # 显式关闭触发器递归（默认即 OFF，防将来被全局打开）：
    # 触发器体内的 UPDATE 不再触发触发器，触碰/补全逻辑因此安全不循环
    conn.execute('PRAGMA recursive_triggers = OFF')
    # 注意：与 Node 版一致，不启用 foreign_keys 强制（Node 仅开 WAL）。
    # 建表语句中的 FK 声明在 Node 下同样不生效，级联删除由业务代码手动完成；
    # 强制 FK 会导致合法请求（如缺省 projectId=1 的悬空引用）500，行为与原版分歧。
    conn.executescript(SCHEMA)
    _migrate_sync_columns(conn)  # 老库补列（新库 no-op）；须在建触发器之前（老库无新列时触发器解析会失败）
    conn.executescript(_triggers_sql())
    return conn


# 已打开的用户库连接缓存：user_id -> (conn, RLock)，对应 Node 版的 openConnections Map
_open = {}
_open_guard = threading.Lock()


def user_db_ctx(user_id, seed=True):
    """获取（或首次打开并初始化）指定用户的独立数据库，返回在其锁内执行的上下文管理器

    :param seed: 首次建库时是否播种默认清单/节日（云端账号的镜像库传 False——
                 内容完全来自远程同步，播种会在首拉前污染镜像）
    """
    with _open_guard:
        entry = _open.get(user_id)
        if entry is None:
            conn = open_database_at_path(user_db_path(user_id))
            if seed:
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


# 默认清单/节日使用固定 guid：同步两侧（镜像库与服务端库）各自播种时不会产生重复行
DEFAULT_PROJECTS = [
    ('收集箱', '#4096ff', '', 'TASK', 0, 'p-collect'),
    ('生活', '#484553', '🍎', 'TASK', 1, 'p-life'),
    ('工作任务清单', '#ff6161', '💼', 'TASK', 2, 'p-work'),
]

# 预置节日（与原版一致的农历节日 + 公历节日；农历条目的 date 存农历月-日，年份忽略）
DEFAULT_COUNTDOWNS = [
    ('元旦', 'festival', '2026-01-01', 0, 'cd-newyear'),
    ('除夕', 'festival', '2000-12-30', 1, 'cd-chuxi'),
    ('春节', 'festival', '2000-01-01', 1, 'cd-chunjie'),
    ('元宵节', 'festival', '2000-01-15', 1, 'cd-yuanxiao'),
    ('端午节', 'festival', '2000-05-05', 1, 'cd-duanwu'),
    ('中秋节', 'festival', '2000-08-15', 1, 'cd-zhongqiu'),
    ('国庆节', 'festival', '2026-10-01', 0, 'cd-guoqing'),
    ('圣诞节', 'festival', '2026-12-25', 0, 'cd-shengdan'),
]


def ensure_default_data(conn):
    n = conn.execute('SELECT COUNT(*) AS n FROM projects WHERE is_deleted = 0').fetchone()['n']
    if n == 0:
        conn.executemany(
            'INSERT INTO projects (name, color, emoji, kind, sort_order, guid) VALUES (?,?,?,?,?,?)',
            DEFAULT_PROJECTS,
        )
    _seed_countdowns(conn)


def _seed_countdowns(conn):
    n = conn.execute('SELECT COUNT(*) AS n FROM countdowns WHERE is_deleted = 0').fetchone()['n']
    if n > 0:
        return
    conn.executemany(
        'INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, sort_order, guid) VALUES (?,?,?,?,?,?,?)',
        [(title, type_, date, is_lunar, 1, i, guid)
         for i, (title, type_, date, is_lunar, guid) in enumerate(DEFAULT_COUNTDOWNS)],
    )
