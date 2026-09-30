"""外部清单应用备份 CSV 导入（口径 1:1 对应原 Node 版 server/import-csv.js）

- 可作为模块函数被 /api/import 调用，也可独立 CLI 运行
- CLI 用法：python import_csv.py <备份.csv>（目标库由 LIUG_DB_PATH 指定，默认 data/schedule.db）
- 注：leadingEmoji 的 \p{Extended_Pictographic} 语法需要 regex 第三方包（Python 内置 re 不支持）
"""
import csv
import io
import os
from datetime import datetime, timedelta
from pathlib import Path

import regex as re

from db import open_database_at_path

PALETTE = ['#484553', '#ff6161', '#ff9f1a', '#2d8ff0', '#8b6ff0', '#46c793', '#ffb1da', '#9856cd', '#299ba8', '#7cbe1e']

EMOJI_RE = re.compile(r'^(\p{Extended_Pictographic}|\p{Emoji_Presentation})(\uFE0F)?\s*')
UTC_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})')

_TZ = {
    'Asia/Shanghai': 480, 'Asia/Chongqing': 480, 'Asia/Urumqi': 480, 'Asia/Harbin': 480,
    'Asia/Tokyo': 540, 'Asia/Seoul': 540,
    'UTC': 0, 'Europe/London': 0,
    'America/New_York': -300, 'America/Chicago': -300, 'America/Detroit': -300,
}


def tz_offset_minutes(tz):
    return _TZ.get(tz, 480)  # 缺省按上海（国内导出的常见默认时区）


def leading_emoji(name):
    m = EMOJI_RE.match(name)
    if not m:
        return '', name
    return m.group(0).strip(), name[m.end():].strip()


def to_local_iso(utc, tz_min):
    """CSV 时间形如 2026-08-14T16:00:00+0000（UTC），转成记录时区的本地无时区 ISO"""
    if not utc:
        return None
    m = UTC_RE.match(utc)
    if not m:
        return None
    try:
        d = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6])) + timedelta(minutes=tz_min)
    except ValueError:
        return None
    return d.strftime('%Y-%m-%dT%H:%M:%S')


def import_csv(conn, csv_path, wipe=True):
    raw = Path(csv_path).read_text(encoding='utf-8-sig')
    rows = list(csv.reader(io.StringIO(raw)))
    header_idx = next((i for i, r in enumerate(rows) if r and r[0].startswith('Folder Name')), -1)
    if header_idx < 0:
        raise RuntimeError('未找到 CSV 表头（需要外部清单应用导出的备份 CSV）')
    col_idx = {name: i for i, name in enumerate(rows[header_idx])}

    def get(cells, name):
        idx = col_idx.get(name, -1)
        if idx < 0 or idx >= len(cells):
            return ''
        return cells[idx]

    conn.execute('BEGIN')
    try:
        if wipe:
            for table in ('tasks', 'projects', 'folders'):
                conn.execute(f'DELETE FROM {table}')
        project_map = {}  # listName -> project rowid
        folder_map = {}  # folderName -> folder rowid
        source_id_map = {}  # 源 taskId -> 本库 rowid
        inserted = []  # (源 parentId, 本库 rowid)，第二遍建立父子关系
        color_idx = 0
        n_tasks = 0

        for row in rows[header_idx + 1:]:
            if len(row) < 5:
                continue
            folder_name = get(row, 'Folder Name')
            list_name = get(row, 'List Name')
            title = get(row, 'Title')
            if not list_name and not title:
                continue

            # folder
            folder_id = None
            if folder_name:
                if folder_name not in folder_map:
                    cur = conn.execute('INSERT INTO folders (name) VALUES (?)', (folder_name,))
                    folder_map[folder_name] = cur.lastrowid
                folder_id = folder_map[folder_name]

            # project（清单）：名称前缀 emoji 提取 + 调色板轮转取色
            emoji, clean_name = leading_emoji(list_name)
            if list_name not in project_map:
                kind = (get(row, 'projectKind') or 'TASK').upper()
                color = PALETTE[color_idx % len(PALETTE)]
                color_idx += 1
                cur = conn.execute(
                    'INSERT INTO projects (name, color, emoji, kind, folder_id, sort_order) VALUES (?,?,?,?,?,?)',
                    (clean_name or list_name, color, emoji, kind, folder_id, len(project_map)),
                )
                project_map[list_name] = cur.lastrowid
            project_id = project_map[list_name]

            tz_min = tz_offset_minutes(get(row, 'Timezone') or 'Asia/Shanghai')
            is_all_day = get(row, 'Is All Day') == 'true'
            status = int(float(get(row, 'Status') or '0'))
            priority = int(float(get(row, 'Priority') or '0'))
            # 导出 CSV 的 Order 是 ~1e18 级别大整数，超出 JS 安全范围；按行号映射即可保留原始排序
            order = n_tasks
            created = to_local_iso(get(row, 'Created Time'), tz_min)
            completed = to_local_iso(get(row, 'Completed Time'), tz_min) if status == 2 else None
            repeat = get(row, 'Repeat') or ''
            reminder = get(row, 'Reminder') or ''
            start = to_local_iso(get(row, 'Start Date'), tz_min)
            due = to_local_iso(get(row, 'Due Date'), tz_min)
            if is_all_day:
                if start:
                    start = start[:10] + 'T00:00:00'
                if due:
                    due = due[:10] + 'T00:00:00'
            content = get(row, 'Content') or ''
            tags = ','.join(t.strip() for t in (get(row, 'Tags') or '').split(',') if t.strip())

            cur = conn.execute(
                'INSERT INTO tasks (project_id, parent_id, title, content, is_checklist, tags, start_date, due_date,'
                ' reminder, repeat_flag, priority, status, sort_order, is_all_day, is_floating, created_at, completed_at)'
                ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    project_id, None, title or '(无标题)', content,
                    1 if get(row, 'Is Check list') == 'Y' else 0,
                    tags, start, due,
                    '' if reminder == 'PT0S' else reminder,
                    repeat, priority, status, order,
                    1 if is_all_day else 0,
                    1 if get(row, 'Is Floating') == 'true' else 0,
                    created, completed,
                ),
            )
            n_tasks += 1
            source_id = get(row, 'taskId')
            if source_id:
                source_id_map[source_id] = cur.lastrowid
            parent_id = get(row, 'parentId')
            if parent_id:
                inserted.append((parent_id, cur.lastrowid))

        # 第二遍：解析子任务的父任务
        for parent_id, rowid in inserted:
            pid = source_id_map.get(parent_id)
            if pid is not None:
                conn.execute('UPDATE tasks SET parent_id = ? WHERE id = ?', (pid, rowid))

        conn.execute('COMMIT')
        return {'ok': True, 'projects': len(project_map), 'folders': len(folder_map), 'tasks': n_tasks}
    except Exception:
        conn.execute('ROLLBACK')
        raise


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='导入外部清单应用备份 CSV')
    parser.add_argument('csv', help='外部清单应用导出的备份 CSV 路径')
    args = parser.parse_args()

    db_path = Path(os.environ.get('LIUG_DB_PATH') or (Path(__file__).resolve().parent.parent / 'data' / 'schedule.db')).resolve()
    conn = open_database_at_path(db_path)
    r = import_csv(conn, args.csv)
    print(f"导入完成: {r['projects']} 个清单, {r['folders']} 个文件夹, {r['tasks']} 条任务")
