import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');

// 用户主库：默认 data/users.db；测试通过 DIDA_USERS_DB_PATH 指向独立文件
export const USERS_DB_PATH = process.env.DIDA_USERS_DB_PATH
  ? path.resolve(process.env.DIDA_USERS_DB_PATH)
  : path.join(DATA_DIR, 'users.db');

export const usersDb = new DatabaseSync(USERS_DB_PATH);
usersDb.exec('PRAGMA journal_mode = WAL');

usersDb.exec(`
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  disabled INTEGER NOT NULL DEFAULT 0,
  sessions_since INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
`);

// 已吊销的会话（登出后令牌立即失效）；过期条目随写入自动清理
usersDb.exec(`
CREATE TABLE IF NOT EXISTS revoked_sessions (
  sig TEXT PRIMARY KEY,
  exp INTEGER NOT NULL
);
`);

// 兼容旧库：补充 sessions_since 列
try {
  usersDb.exec('ALTER TABLE users ADD COLUMN sessions_since INTEGER NOT NULL DEFAULT 0');
} catch {}

// ---------- 密码哈希（scrypt） ----------
export function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(String(password), salt, 64).toString('hex');
  return `scrypt$${salt}$${hash}`;
}

export function verifyPassword(password, stored) {
  try {
    const [scheme, salt, hash] = String(stored || '').split('$');
    if (scheme !== 'scrypt' || !salt || !hash) return false;
    const test = crypto.scryptSync(String(password), salt, 64);
    return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), test);
  } catch {
    return false;
  }
}

// ---------- 会话令牌（无状态 HMAC 签名 Cookie） ----------
const SECRET_PATH = USERS_DB_PATH + '.secret';
let SECRET;
if (fs.existsSync(SECRET_PATH)) {
  SECRET = fs.readFileSync(SECRET_PATH, 'utf8').trim();
} else {
  SECRET = crypto.randomBytes(32).toString('hex');
  fs.writeFileSync(SECRET_PATH, SECRET);
}

const SESSION_TTL_MS = 7 * 24 * 3600 * 1000; // 7 天
export const SESSION_COOKIE = 'dida_session';

export function signSession(userId) {
  const payload = Buffer.from(
    JSON.stringify({ uid: userId, iat: Date.now(), exp: Date.now() + SESSION_TTL_MS })
  ).toString('base64url');
  const sig = crypto.createHmac('sha256', SECRET).update(payload).digest('base64url');
  return `${payload}.${sig}`;
}

/** 校验令牌签名与有效期，返回 { uid, iat, exp } 或 null */
export function verifySessionToken(token) {
  if (!token || typeof token !== 'string') return null;
  const dot = token.lastIndexOf('.');
  if (dot <= 0) return null;
  const payload = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expect = crypto.createHmac('sha256', SECRET).update(payload).digest('base64url');
  const a = Buffer.from(sig);
  const b = Buffer.from(expect);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    if (!data.uid || !data.exp || data.exp < Date.now()) return null;
    return data;
  } catch {
    return null;
  }
}

// ---------- 会话吊销 ----------
/** 登出：吊销单个令牌（令牌本身带有效期，过期条目自动清理） */
export function revokeSession(token) {
  const session = verifySessionToken(token);
  if (!session) return;
  usersDb
    .prepare('INSERT OR IGNORE INTO revoked_sessions (sig, exp) VALUES (?,?)')
    .run(token.slice(token.lastIndexOf('.') + 1), session.exp);
  usersDb.prepare('DELETE FROM revoked_sessions WHERE exp < ?').run(Date.now());
}

/** 令牌是否已被吊销 */
export function isSessionRevoked(token) {
  if (!token) return false;
  const sig = token.slice(token.lastIndexOf('.') + 1);
  return !!usersDb.prepare('SELECT 1 FROM revoked_sessions WHERE sig = ?').get(sig);
}

/** 修改密码等场景：使某用户的所有既有会话立即失效 */
export function revokeAllSessions(userId) {
  usersDb.prepare('UPDATE users SET sessions_since = ? WHERE id = ?').run(Date.now(), userId);
}

// ---------- 用户 CRUD ----------
export function listUsers() {
  return usersDb
    .prepare('SELECT id, username, role, disabled, created_at FROM users ORDER BY created_at, username')
    .all();
}

export function findUserByUsername(username) {
  return usersDb.prepare('SELECT * FROM users WHERE username = ?').get(String(username || ''));
}

export function findUserById(id) {
  return usersDb.prepare('SELECT * FROM users WHERE id = ?').get(String(id || ''));
}

export function createUser({ username, password, role = 'user' }) {
  const id = crypto.randomUUID();
  usersDb
    .prepare('INSERT INTO users (id, username, password_hash, role) VALUES (?,?,?,?)')
    .run(id, String(username), hashPassword(password), role === 'admin' ? 'admin' : 'user');
  return findUserById(id);
}

export function adminCount() {
  return usersDb.prepare("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND disabled = 0").get().n;
}

export function publicUser(u) {
  return u ? { id: u.id, username: u.username, role: u.role, disabled: !!u.disabled, createdAt: u.created_at } : null;
}

// ---------- 首次启动：默认管理员 + 旧单库数据迁移 ----------
export function bootstrapUsers({ userDbPath, legacyDbPath }) {
  const n = usersDb.prepare('SELECT COUNT(*) AS n FROM users').get().n;
  if (n > 0) return;

  const admin = createUser({ username: 'admin', password: 'admin123', role: 'admin' });

  // 生产环境（未重定向用户主库）且存在旧正式库时，把旧数据只读复制为 admin 的用户库。
  // 仅读取 schedule.db（VACUUM INTO），不修改、不删除原文件。
  if (!process.env.DIDA_USERS_DB_PATH && legacyDbPath && fs.existsSync(legacyDbPath)) {
    try {
      const dest = userDbPath(admin.id);
      const src = new DatabaseSync(legacyDbPath, { readOnly: true });
      src.exec(`VACUUM INTO '${dest.replace(/'/g, "''")}'`);
      src.close();
      console.log('[users] 已将原有 schedule.db 数据迁移为 admin 账户的独立数据库');
    } catch (e) {
      console.error('[users] 旧数据迁移失败（将使用全新的 admin 数据库）:', e.message);
    }
  }
  console.log('[users] 已创建默认管理员账户：admin / admin123（请尽快修改密码）');
}
