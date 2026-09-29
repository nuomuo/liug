import express from 'express';
import cors from 'cors';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getUserDb, ensureDefaultData, userDbPath } from './db.js';
import { importCsv } from './import-csv.js';
import { getHolidays } from './holidays.js';
import {
  bootstrapUsers,
  findUserById,
  findUserByUsername,
  verifyPassword,
  hashPassword,
  publicUser,
  signSession,
  verifySessionToken,
  revokeSession,
  isSessionRevoked,
  revokeAllSessions,
  SESSION_COOKIE,
} from './users.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json({ limit: '20mb' }));

// ---------- serialization ----------
// node:sqlite returns out-of-range integers as BigInt; make them JSON-safe
function deBigint(obj) {
  return JSON.parse(JSON.stringify(obj, (_, v) => (typeof v === 'bigint' ? Number(v) : v)));
}

// 北京时间（UTC+8）本地时刻，与滴答备份 CSV 的 Asia/Shanghai 口径一致
function beijingNowIso() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().replace('Z', '');
}

function taskToJson(row) {
  if (!row) return null;
  return deBigint({
    id: row.id,
    projectId: row.project_id,
    parentId: row.parent_id,
    title: row.title,
    content: row.content,
    isChecklist: !!row.is_checklist,
    tags: row.tags ? row.tags.split(',').filter(Boolean) : [],
    startDate: row.start_date,
    dueDate: row.due_date,
    priority: row.priority,
    status: row.status,
    sortOrder: row.sort_order,
    isAllDay: !!row.is_all_day,
    isFloating: !!row.is_floating,
    reminder: row.reminder,
    repeatFlag: row.repeat_flag,
    createdAt: row.created_at,
    completedAt: row.completed_at,
  });
}

function projectToJson(row) {
  if (!row) return null;
  return deBigint({
    id: row.id,
    name: row.name,
    color: row.color,
    emoji: row.emoji,
    kind: row.kind,
    folderId: row.folder_id,
    sortOrder: row.sort_order,
  });
}

function folderToJson(row) {
  return row ? { id: row.id, name: row.name } : null;
}

function countdownToJson(row) {
  if (!row) return null;
  return deBigint({
    id: row.id,
    title: row.title,
    type: row.type,
    date: row.date,
    isLunar: !!row.is_lunar,
    repeatYearly: !!row.repeat_yearly,
    pinned: !!row.pinned,
    sortOrder: row.sort_order,
  });
}

// ---------- cookie 解析（免依赖） ----------
function parseCookies(req) {
  const header = req.headers.cookie;
  const out = {};
  if (!header) return out;
  for (const part of header.split(';')) {
    const idx = part.indexOf('=');
    if (idx < 0) continue;
    out[part.slice(0, idx).trim()] = decodeURIComponent(part.slice(idx + 1).trim());
  }
  return out;
}

// ---------- 鉴权中间件 ----------
// 除 /api/auth/login 与公共数据接口（/api/holidays）外，所有 /api/* 都需要有效会话，并挂载 req.user / req.userDb
app.use('/api', (req, res, next) => {
  if (req.path === '/auth/login' || req.path === '/holidays') return next();
  const token = parseCookies(req)[SESSION_COOKIE];
  const session = verifySessionToken(token);
  if (!session) return res.status(401).json({ error: '未登录或会话已过期' });
  const user = findUserById(session.uid);
  if (!user) return res.status(401).json({ error: '账户不存在' });
  if (user.disabled) return res.status(403).json({ error: '账户已被禁用' });
  // 已登出吊销的令牌 / 修改密码之前的旧令牌一律失效
  if (isSessionRevoked(token) || (user.sessions_since || 0) > session.iat) {
    return res.status(401).json({ error: '会话已失效，请重新登录' });
  }
  req.user = user;
  req.userDb = getUserDb(user.id);
  next();
});

// ---------- 认证 ----------
app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  const user = findUserByUsername(username);
  if (!user || !verifyPassword(password, user.password_hash)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }
  if (user.disabled) {
    return res.status(403).json({ error: '账户已被禁用，请联系管理员' });
  }
  res.setHeader(
    'Set-Cookie',
    `${SESSION_COOKIE}=${signSession(user.id)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${7 * 24 * 3600}`
  );
  res.json({ user: publicUser(user) });
});

app.post('/api/auth/logout', (req, res) => {
  // 服务端吊销当前令牌（即使客户端保留 cookie 也无法继续使用）
  revokeSession(parseCookies(req)[SESSION_COOKIE]);
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`);
  res.json({ ok: true });
});

app.get('/api/auth/me', (req, res) => {
  res.json({ user: publicUser(req.user) });
});

// 普通用户修改自己的密码（修改后其他设备会全部下线，当前会话自动续期）
app.post('/api/auth/change-password', (req, res) => {
  const { oldPassword, newPassword } = req.body || {};
  if (!verifyPassword(oldPassword, req.user.password_hash)) {
    return res.status(400).json({ error: '原密码错误' });
  }
  if (typeof newPassword !== 'string' || newPassword.length < 6) {
    return res.status(400).json({ error: '新密码至少需要 6 个字符' });
  }
  usersDb.prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(hashPassword(newPassword), req.user.id);
  revokeAllSessions(req.user.id);
  // 重新签发当前会话，避免改密后立刻被踢出
  res.setHeader(
    'Set-Cookie',
    `${SESSION_COOKIE}=${signSession(req.user.id)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${7 * 24 * 3600}`
  );
  res.json({ ok: true });
});

// ---------- 官方节假日（公共数据，无需登录） ----------
// 国务院办公厅公布的节假日安排（含调休补班），服务端缓存后转发
app.get('/api/holidays', async (req, res) => {
  const now = new Date(Date.now() + 8 * 3600 * 1000); // 北京时间
  const year = parseInt(req.query.year, 10) || now.getUTCFullYear();
  if (!Number.isInteger(year) || year < 2007 || year > 2100) {
    return res.status(400).json({ error: '年份需在 2007-2100 之间' });
  }
  try {
    res.json(await getHolidays(year));
  } catch (e) {
    res.status(502).json({ error: '获取节假日数据失败：' + (e.message || '未知错误') });
  }
});

// ---------- bootstrap ----------
app.get('/api/bootstrap', (req, res) => {
  const db = req.userDb;
  const folders = db.prepare('SELECT * FROM folders ORDER BY id').all().map(folderToJson);
  const projects = db
    .prepare('SELECT * FROM projects WHERE is_deleted = 0 ORDER BY sort_order, id')
    .all()
    .map(projectToJson);
  const tasks = db
    .prepare('SELECT * FROM tasks WHERE is_deleted = 0 AND parent_id IS NULL ORDER BY sort_order, id')
    .all()
    .map(taskToJson);
  const subtasks = db
    .prepare('SELECT * FROM tasks WHERE is_deleted = 0 AND parent_id IS NOT NULL ORDER BY sort_order, id')
    .all()
    .map(taskToJson);
  const countdowns = db
    .prepare('SELECT * FROM countdowns WHERE is_deleted = 0 ORDER BY pinned DESC, sort_order, id')
    .all()
    .map(countdownToJson);
  res.json({ folders, projects, tasks, subtasks, countdowns });
});

// ---------- tasks ----------
app.get('/api/tasks', (req, res) => {
  const rows = req.userDb
    .prepare('SELECT * FROM tasks WHERE is_deleted = 0 ORDER BY sort_order, id')
    .all();
  res.json(rows.map(taskToJson));
});

const TASK_FIELDS = {
  projectId: 'project_id',
  parentId: 'parent_id',
  title: 'title',
  content: 'content',
  isChecklist: 'is_checklist',
  tags: 'tags',
  startDate: 'start_date',
  dueDate: 'due_date',
  priority: 'priority',
  status: 'status',
  sortOrder: 'sort_order',
  isAllDay: 'is_all_day',
  isFloating: 'is_floating',
  reminder: 'reminder',
  repeatFlag: 'repeat_flag',
  completedAt: 'completed_at',
};

app.post('/api/tasks', (req, res) => {
  const db = req.userDb;
  const b = req.body || {};
  const stmt = db.prepare(`INSERT INTO tasks
    (project_id, parent_id, title, content, is_checklist, tags, start_date, due_date, priority, status, sort_order, is_all_day, is_floating, reminder, repeat_flag, created_at, completed_at)
    VALUES (@project_id, @parent_id, @title, @content, @is_checklist, @tags, @start_date, @due_date, @priority, @status, @sort_order, @is_all_day, @is_floating, @reminder, @repeat_flag, @created_at, @completed_at)`);
  const minOrder = db
    .prepare('SELECT COALESCE(MIN(sort_order), 0) AS m FROM tasks WHERE is_deleted = 0')
    .get().m;
  const info = stmt.run({
    project_id: b.projectId ?? 1,
    parent_id: b.parentId ?? null,
    title: b.title ?? '',
    content: b.content ?? '',
    is_checklist: b.isChecklist ? 1 : 0,
    tags: Array.isArray(b.tags) ? b.tags.join(',') : (b.tags ?? ''),
    start_date: b.startDate ?? null,
    due_date: b.dueDate ?? null,
    priority: b.priority ?? 0,
    status: b.status ?? 0,
    sort_order: b.sortOrder ?? minOrder - 1,
    is_all_day: b.isAllDay === false ? 0 : 1,
    is_floating: b.isFloating ? 1 : 0,
    reminder: b.reminder ?? '',
    repeat_flag: b.repeatFlag ?? '',
    created_at: beijingNowIso(),
    completed_at: b.completedAt ?? null,
  });
  const row = db.prepare('SELECT * FROM tasks WHERE id = ?').get(info.lastInsertRowid);
  res.json(taskToJson(row));
});

app.put('/api/tasks/:id', (req, res) => {
  const db = req.userDb;
  const id = Number(req.params.id);
  const existing = db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'task not found' });
  const sets = [];
  const params = {};
  for (const [k, col] of Object.entries(TASK_FIELDS)) {
    if (req.body[k] !== undefined) {
      let v = req.body[k];
      if (k === 'tags') v = Array.isArray(v) ? v.join(',') : v;
      if (['isChecklist', 'isAllDay', 'isFloating'].includes(k)) v = v ? 1 : 0;
      if (k === 'parentId' && v === null) v = null;
      sets.push(`${col} = @${k}`);
      params[k] = v;
    }
  }
  if (sets.length) {
    db.prepare(`UPDATE tasks SET ${sets.join(', ')} WHERE id = @id`).run({ ...params, id });
  }
  const row = db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
  res.json(taskToJson(row));
});

app.delete('/api/tasks/:id', (req, res) => {
  req.userDb
    .prepare('UPDATE tasks SET is_deleted = 1 WHERE id = ? OR parent_id = ?')
    .run(Number(req.params.id), Number(req.params.id));
  res.json({ ok: true });
});

// ---------- projects ----------
app.post('/api/projects', (req, res) => {
  const db = req.userDb;
  const b = req.body || {};
  const maxOrder = db
    .prepare('SELECT COALESCE(MAX(sort_order), 0) AS m FROM projects')
    .get().m;
  const info = db
    .prepare('INSERT INTO projects (name, color, emoji, kind, folder_id, sort_order) VALUES (?,?,?,?,?,?)')
    .run(b.name ?? '新清单', b.color ?? '#484553', b.emoji ?? '', b.kind ?? 'TASK', b.folderId ?? null, maxOrder + 1);
  const row = db.prepare('SELECT * FROM projects WHERE id = ?').get(info.lastInsertRowid);
  res.json(projectToJson(row));
});

app.put('/api/projects/:id', (req, res) => {
  const db = req.userDb;
  const id = Number(req.params.id);
  const b = req.body || {};
  const sets = [];
  const params = { id };
  for (const [k, col] of [['name', 'name'], ['color', 'color'], ['emoji', 'emoji'], ['folderId', 'folder_id']]) {
    if (b[k] !== undefined) {
      sets.push(`${col} = @${k}`);
      params[k] = b[k];
    }
  }
  if (sets.length) db.prepare(`UPDATE projects SET ${sets.join(', ')} WHERE id = @id`).run(params);
  const row = db.prepare('SELECT * FROM projects WHERE id = ?').get(id);
  res.json(projectToJson(row));
});

app.delete('/api/projects/:id', (req, res) => {
  const db = req.userDb;
  const id = Number(req.params.id);
  if (id === 1) return res.status(400).json({ error: '收集箱不可删除' });
  db.prepare('UPDATE projects SET is_deleted = 1 WHERE id = ?').run(id);
  db.prepare('UPDATE tasks SET is_deleted = 1 WHERE project_id = ?').run(id);
  res.json({ ok: true });
});

// ---------- search ----------
app.get('/api/search', (req, res) => {
  const q = String(req.query.q || '').trim();
  if (!q) return res.json({ tasks: [] });
  const like = `%${q.replace(/[%_]/g, '')}%`;
  const rows = req.userDb
    .prepare(
      `SELECT * FROM tasks WHERE is_deleted = 0 AND (title LIKE ? OR content LIKE ? OR tags LIKE ?) ORDER BY due_date IS NULL, due_date LIMIT 200`
    )
    .all(like, like, like);
  res.json({ tasks: rows.map(taskToJson) });
});

// ---------- countdowns ----------
app.post('/api/countdowns', (req, res) => {
  const db = req.userDb;
  const b = req.body || {};
  const maxOrder = db.prepare('SELECT COALESCE(MAX(sort_order), 0) AS m FROM countdowns').get().m;
  const info = db
    .prepare('INSERT INTO countdowns (title, type, date, is_lunar, repeat_yearly, pinned, sort_order) VALUES (?,?,?,?,?,?,?)')
    .run(b.title ?? '纪念日', b.type ?? 'countdown', b.date ?? '', b.isLunar ? 1 : 0, b.repeatYearly === false ? 0 : 1, b.pinned ? 1 : 0, maxOrder + 1);
  const row = db.prepare('SELECT * FROM countdowns WHERE id = ?').get(info.lastInsertRowid);
  res.json(countdownToJson(row));
});

app.put('/api/countdowns/:id', (req, res) => {
  const db = req.userDb;
  const id = Number(req.params.id);
  const existing = db.prepare('SELECT * FROM countdowns WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'countdown not found' });
  const FIELDS = { title: 'title', type: 'type', date: 'date', isLunar: 'is_lunar', repeatYearly: 'repeat_yearly', pinned: 'pinned', sortOrder: 'sort_order' };
  const sets = [];
  const params = { id };
  for (const [k, col] of Object.entries(FIELDS)) {
    if (req.body[k] !== undefined) {
      let v = req.body[k];
      if (k === 'isLunar' || k === 'repeatYearly' || k === 'pinned') v = v ? 1 : 0;
      sets.push(`${col} = @${k}`);
      params[k] = v;
    }
  }
  if (sets.length) db.prepare(`UPDATE countdowns SET ${sets.join(', ')} WHERE id = @id`).run(params);
  const row = db.prepare('SELECT * FROM countdowns WHERE id = ?').get(id);
  res.json(countdownToJson(row));
});

app.delete('/api/countdowns/:id', (req, res) => {
  req.userDb.prepare('UPDATE countdowns SET is_deleted = 1 WHERE id = ?').run(Number(req.params.id));
  res.json({ ok: true });
});

// ---------- import ----------
app.post('/api/import', (req, res) => {
  const csvPath = req.body?.csvPath;
  if (!csvPath) return res.status(400).json({ error: 'csvPath required' });
  try {
    const result = importCsv(req.userDb, csvPath);
    res.json(result);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

// 重置当前用户自己的数据（不影响其他用户）
app.post('/api/reset', (req, res) => {
  const db = req.userDb;
  db.exec('DELETE FROM tasks; DELETE FROM projects; DELETE FROM folders;');
  ensureDefaultData(db);
  res.json({ ok: true });
});

// ---------- static client (production build) ----------
const distDir = path.join(__dirname, '..', 'client', 'dist');
app.use(express.static(distDir));
app.get(/^(?!\/api\/).*/, (req, res) => {
  res.sendFile(path.join(distDir, 'index.html'));
});

// 首次启动：初始化用户主库（默认 admin/admin123 + 旧数据迁移）
const LEGACY_DB = path.join(__dirname, '..', 'data', 'schedule.db');
bootstrapUsers({ userDbPath, legacyDbPath: LEGACY_DB });

const PORT = process.env.PORT || 4300;
app.listen(PORT, () => {
  console.log(`[server] running at http://localhost:${PORT}`);
});
