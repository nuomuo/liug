import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDatabaseAtPath } from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Parse a quoted CSV field stream (RFC4180-ish: "" escaping, commas, newlines inside quotes)
function parseCsvLine(line) {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else inQuotes = false;
      } else cur += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

function splitRecords(text) {
  // split into logical records respecting quotes
  const records = [];
  let cur = '';
  let inQuotes = false;
  for (const ch of text) {
    if (ch === '"') inQuotes = !inQuotes;
    if (ch === '\n' && !inQuotes) {
      records.push(cur);
      cur = '';
    } else if (ch !== '\r') cur += ch;
  }
  if (cur.trim()) records.push(cur);
  return records;
}

const PALETTE = ['#484553', '#ff6161', '#ff9f1a', '#2d8ff0', '#8b6ff0', '#46c793', '#ffb1da', '#9856cd', '#299ba8', '#7cbe1e'];

function leadingEmoji(name) {
  const m = name.match(/^(\p{Extended_Pictographic}|\p{Emoji_Presentation})(\uFE0F)?\s*/u);
  if (!m) return { emoji: '', name };
  return { emoji: m[0].trim(), name: name.slice(m[0].length).trim() };
}

// Dida dates look like 2026-08-14T16:00:00+0000 with timezone Asia/Shanghai.
// Convert to local-naive ISO "YYYY-MM-DDTHH:mm:ss" in the record's timezone.
function toLocalIso(utc, tzOffsetMinutes) {
  if (!utc) return null;
  const m = utc.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  d.setUTCMinutes(d.getUTCMinutes() + tzOffsetMinutes);
  const p = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate()) +
    'T' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds())
  );
}

function tzOffsetMinutes(tz) {
  if (tz === 'Asia/Shanghai' || tz === 'Asia/Chongqing' || tz === 'Asia/Urumqi' || tz === 'Asia/Harbin') return 480;
  if (tz === 'Asia/Tokyo' || tz === 'Asia/Seoul') return 540;
  if (tz === 'UTC' || tz === 'Europe/London') return 0;
  if (tz === 'America/New_York' || tz === 'America/Chicago' || tz === 'America/Detroit') return -300;
  // fall back to Shanghai (dida CN default)
  return 480;
}

// db: 目标数据库连接（多用户模式下为当前登录用户的独立库）
export function importCsv(db, csvPath, { wipe = true } = {}) {
  const raw = fs.readFileSync(csvPath, 'utf8').replace(/^\uFEFF/, '');
  const records = splitRecords(raw);
  let headerIdx = records.findIndex((r) => r.replace(/"/g, '').startsWith('Folder Name'));
  if (headerIdx < 0) throw new Error('未找到 CSV 表头（需要滴答清单导出的备份 CSV）');
  const headers = parseCsvLine(records[headerIdx]).map((h) => h.replace(/^"|"$/g, ''));
  const col = (name) => headers.indexOf(name);

  const insertProject = db.prepare(
    'INSERT INTO projects (name, color, emoji, kind, folder_id, sort_order) VALUES (?,?,?,?,?,?)'
  );
  const insertFolder = db.prepare('INSERT INTO folders (name) VALUES (?)');
  const findProject = db.prepare('SELECT * FROM projects WHERE name = ? AND is_deleted = 0');
  const findFolder = db.prepare('SELECT * FROM folders WHERE name = ?');
  const insertTask = db.prepare(`INSERT INTO tasks
    (project_id, parent_id, title, content, is_checklist, tags, start_date, due_date, reminder, repeat_flag,
     priority, status, sort_order, is_all_day, is_floating, created_at, completed_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
  const setParent = db.prepare('UPDATE tasks SET parent_id = ? WHERE id = ?');

  const run = () => {
    db.exec('BEGIN');
    try {
      if (wipe) {
        db.exec('DELETE FROM tasks; DELETE FROM projects; DELETE FROM folders;');
      }
      const projectMap = new Map(); // listName -> project rowid
      const folderMap = new Map();
      const didaIdMap = new Map(); // dida taskId -> rowid
      let colorIdx = 0;
      let nTasks = 0;

      for (let i = headerIdx + 1; i < records.length; i++) {
        const cells = parseCsvLine(records[i]);
        if (cells.length < 5) continue;
        const get = (name) => {
          const idx = col(name);
          return idx >= 0 ? (cells[idx] ?? '') : '';
        };

        const folderName = get('Folder Name');
        const listName = get('List Name');
        const title = get('Title');
        if (!listName && !title) continue;

        // folder
        let folderId = null;
        if (folderName) {
          if (!folderMap.has(folderName)) {
            const info = insertFolder.run(folderName);
            folderMap.set(folderName, Number(info.lastInsertRowid));
          }
          folderId = folderMap.get(folderName);
        }

        // project (list)
        let projectId;
        const { emoji, name: cleanName } = leadingEmoji(listName);
        if (!projectMap.has(listName)) {
          const kind = (get('projectKind') || 'TASK').toUpperCase();
          const color = PALETTE[colorIdx++ % PALETTE.length];
          const info = insertProject.run(cleanName || listName, color, emoji, kind, folderId, projectMap.size);
          projectMap.set(listName, Number(info.lastInsertRowid));
        }
        projectId = projectMap.get(listName);

        const tzMin = tzOffsetMinutes(get('Timezone') || 'Asia/Shanghai');
        const isAllDay = get('Is All Day') === 'true';
        const status = Number(get('Status') || '0');
        const priority = Number(get('Priority') || '0');
        // dida 的 Order 是 ~1e18 级别的大整数，超出 JS 安全范围；按行号顺序映射即可保留原始排序
        const order = nTasks;
        const created = toLocalIso(get('Created Time'), tzMin);
        const completed = status === 2 ? toLocalIso(get('Completed Time'), tzMin) : null;
        const repeat = get('Repeat') || '';
        const reminder = get('Reminder') || '';
        let start = toLocalIso(get('Start Date'), tzMin);
        let due = toLocalIso(get('Due Date'), tzMin);
        if (isAllDay) {
          if (start) start = start.slice(0, 10) + 'T00:00:00';
          if (due) due = due.slice(0, 10) + 'T00:00:00';
        }
        const content = get('Content') || '';
        const tags = (get('Tags') || '')
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
          .join(',');

        const info = insertTask.run(
          projectId,
          null,
          title || '(无标题)',
          content,
          get('Is Check list') === 'Y' ? 1 : 0,
          tags,
          start,
          due,
          reminder === 'PT0S' ? '' : reminder,
          repeat,
          priority,
          status,
          order,
          isAllDay ? 1 : 0,
          get('Is Floating') === 'true' ? 1 : 0,
          created,
          completed
        );
        nTasks++;
        const didaId = get('taskId');
        const rowid = Number(info.lastInsertRowid);
        if (didaId) didaIdMap.set(didaId, rowid);
        cells.__rowid = rowid;
        cells.__parentId = get('parentId');
        records[i] = cells; // keep for second pass
      }

      // second pass: resolve subtask parents
      for (let i = headerIdx + 1; i < records.length; i++) {
        const cells = records[i];
        if (!Array.isArray(cells) || !cells.__rowid) continue;
        const pid = cells.__parentId;
        if (pid && didaIdMap.has(pid)) {
          setParent.run(didaIdMap.get(pid), cells.__rowid);
        }
      }
      db.exec('COMMIT');
      return { projects: projectMap.size, folders: folderMap.size, tasks: nTasks };
    } catch (e) {
      db.exec('ROLLBACK');
      throw e;
    }
  };

  const result = run();
  return { ok: true, ...result };
}

// CLI usage: node import-csv.js <path-to-csv>（默认写入单库 data/schedule.db，可用 DIDA_DB_PATH 指定）
if (process.argv[1] && process.argv[1].endsWith('import-csv.js')) {
  const csvPath = process.argv[2];
  if (!csvPath) {
    console.error('用法: node import-csv.js <滴答清单备份.csv>');
    process.exit(1);
  }
  const dbPath = process.env.DIDA_DB_PATH
    ? path.resolve(process.env.DIDA_DB_PATH)
    : path.join(__dirname, '..', 'data', 'schedule.db');
  const db = openDatabaseAtPath(dbPath);
  const r = importCsv(db, csvPath);
  console.log(`导入完成: ${r.projects} 个清单, ${r.folders} 个文件夹, ${r.tasks} 条任务`);
}
