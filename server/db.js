import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');

// 用户数据目录：每个用户一个独立 SQLite 文件（文件名 = 用户唯一 ID）；
// 测试通过 DIDA_USERS_DIR 指向独立目录，避免污染正式用户数据
export const USERS_DIR = process.env.DIDA_USERS_DIR
  ? path.resolve(process.env.DIDA_USERS_DIR)
  : path.join(DATA_DIR, 'users');
if (!fs.existsSync(USERS_DIR)) fs.mkdirSync(USERS_DIR, { recursive: true });

export function userDbPath(userId) {
  return path.join(USERS_DIR, `${userId}.db`);
}

const SCHEMA = `
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
`;

// 已打开的用户库连接缓存（按用户 ID）
const openConnections = new Map();

/** 打开并初始化任意路径的数据库（建表 + WAL） */
export function openDatabaseAtPath(dbPath) {
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec(SCHEMA);
  return db;
}

/** 获取（或打开并初始化）指定用户的独立数据库 */
export function getUserDb(userId) {
  let db = openConnections.get(userId);
  if (db) return db;
  db = openDatabaseAtPath(userDbPath(userId));
  ensureDefaultData(db);
  openConnections.set(userId, db);
  return db;
}

/** 关闭某个用户的连接（用于删除用户前释放文件句柄） */
export function closeUserDb(userId) {
  const db = openConnections.get(userId);
  if (db) {
    try {
      db.close();
    } catch {}
    openConnections.delete(userId);
  }
}

/** 删除某个用户的数据库文件（含 WAL/SHM 附属文件） */
export function deleteUserDbFile(userId) {
  closeUserDb(userId);
  for (const suffix of ['', '-wal', '-shm']) {
    const p = userDbPath(userId) + suffix;
    if (fs.existsSync(p)) fs.unlinkSync(p);
  }
}

export function ensureDefaultData(db) {
  const count = db.prepare('SELECT COUNT(*) AS n FROM projects WHERE is_deleted = 0').get().n;
  if (count === 0) {
    const insertProject = db.prepare(
      'INSERT INTO projects (name, color, emoji, kind, sort_order) VALUES (?,?,?,?,?)'
    );
    insertProject.run('收集箱', '#4096ff', '', 'TASK', 0);
    insertProject.run('生活', '#484553', '🍎', 'TASK', 1);
    insertProject.run('工作任务清单', '#ff6161', '💼', 'TASK', 2);
  }
  seedCountdowns(db);
}

// 预置节日（与原版一致的农历节日 + 公历节日；农历条目的 date 存农历月-日，年份忽略）
const DEFAULT_COUNTDOWNS = [
  ['元旦', 'festival', '2026-01-01', 0],
  ['除夕', 'festival', '2000-12-30', 1],
  ['春节', 'festival', '2000-01-01', 1],
  ['元宵节', 'festival', '2000-01-15', 1],
  ['端午节', 'festival', '2000-05-05', 1],
  ['中秋节', 'festival', '2000-08-15', 1],
  ['国庆节', 'festival', '2026-10-01', 0],
  ['圣诞节', 'festival', '2026-12-25', 0],
];

function seedCountdowns(db) {
  const n = db.prepare('SELECT COUNT(*) AS n FROM countdowns WHERE is_deleted = 0').get().n;
  if (n > 0) return;
  const insert = db.prepare(
    'INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, sort_order) VALUES (?,?,?,?,?,?)'
  );
  DEFAULT_COUNTDOWNS.forEach(([title, type, date, isLunar], i) => {
    insert.run(title, type, date, isLunar, 1, i);
  });
}
