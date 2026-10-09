"""同步核心：快照构建 / LWW 合并 / 幂等应用（guid 空间，服务端与桌面镜像共用）

协议（POST /api/sync，请求与响应同构）：
    请求  {snapshot: <客户端快照>}          → 服务端合并并应用
    响应  {snapshot: <合并后的全量快照>}     → 客户端 verbatim 应用到本地镜像

快照结构（含软删除行；FK 以 guid 引用，跨库无自增 id 冲突）：
    {
      'folders':    [{guid, name, updatedAt}],
      'projects':   [{guid, name, color, emoji, kind, folderGuid, sortOrder, isDeleted, updatedAt}],
      'tasks':      [{guid, projectGuid, parentGuid, title, ..., isDeleted, updatedAt}],
      'countdowns': [{guid, title, type, date, isLunar, repeatYearly, pinned, sortOrder, isDeleted, updatedAt}],
      'tombstones': [{table, guid, deletedAt}],   # 硬删除墓碑（reset / CSV 导入 wipe）
    }

合并规则（merge_snapshots，两端收敛到同一结果）：
    - 行：按 guid 取并集，updatedAt 新者胜；相等时保留第一参数侧（调用方约定传服务端，
      tie 不会形成「你推我推」的循环）
    - 墓碑：并集，deletedAt 取大
    - 墓碑 vs 行：行 updatedAt 更新则行复活（丢弃墓碑），否则墓碑胜出（行不进合并结果）

应用规则（apply_snapshot，幂等，显式带 updated_at 因此不触碰触发器）：
    - baseline 中存在但合并结果缺失的 guid → 硬删除（触发器顺带留墓碑，幂等）
    - 行不存在 → INSERT；本地 updated_at 严格更旧 → UPDATE；否则跳过（不动时间戳）
    - tasks 按父子关系拓扑排序后插入，parent_id 一次到位（无需事后修正，避免触发触碰）
"""
import time

from core.db import SYNC_TABLES

TABLES = ('folders', 'projects', 'tasks', 'countdowns')

# 行协议键 -> 库列（每表数据列；guid/updated_at/FK 列单独处理）
ROW_COLS = {
    'folders': {'name': 'name'},
    'projects': {'name': 'name', 'color': 'color', 'emoji': 'emoji', 'kind': 'kind',
                 'sortOrder': 'sort_order', 'isDeleted': 'is_deleted'},
    'tasks': {'title': 'title', 'content': 'content', 'isChecklist': 'is_checklist', 'tags': 'tags',
              'startDate': 'start_date', 'dueDate': 'due_date', 'priority': 'priority', 'status': 'status',
              'sortOrder': 'sort_order', 'isAllDay': 'is_all_day', 'isFloating': 'is_floating',
              'reminder': 'reminder', 'repeatFlag': 'repeat_flag', 'progress': 'progress',
              'createdAt': 'created_at', 'completedAt': 'completed_at', 'isDeleted': 'is_deleted'},
    'countdowns': {'title': 'title', 'type': 'type', 'date': 'date', 'isLunar': 'is_lunar',
                   'repeatYearly': 'repeat_yearly', 'pinned': 'pinned', 'sortOrder': 'sort_order',
                   'isDeleted': 'is_deleted'},
}

# FK：本地列 -> (行协议键, 引用表)
ROW_FKS = {
    'projects': {'folder_id': ('folderGuid', 'folders')},
    'tasks': {'project_id': ('projectGuid', 'projects'), 'parent_id': ('parentGuid', 'tasks')},
}

TOMBSTONE_RETAIN_DAYS = 90  # 墓碑保留期（超过后清理；极老的对端复活风险可忽略）


# ---------- 快照构建 ----------
def build_snapshot(conn):
    """读取全量数据（含软删除行）为 guid 空间的快照"""
    id_to_guid = {t: {r['id']: r['guid'] for r in conn.execute(f'SELECT id, guid FROM {t}')}
                  for t in TABLES}
    snap = {t: [] for t in TABLES}
    snap['tombstones'] = []

    for t in TABLES:
        for r in conn.execute(f'SELECT * FROM {t}'):
            row = {'guid': r['guid'], 'updatedAt': r['updated_at']}
            for key, col in ROW_COLS[t].items():
                row[key] = r[col]
            for col, (key, ref) in ROW_FKS.get(t, {}).items():
                row[key] = id_to_guid[ref].get(r[col])
            snap[t].append(row)

    for r in conn.execute('SELECT table_name, guid, deleted_at FROM _sync_tombstones'):
        if r['table_name'] in TABLES:
            snap['tombstones'].append({'table': r['table_name'], 'guid': r['guid'], 'deletedAt': r['deleted_at']})
    return snap


# ---------- 合并 ----------
def _later(a, b):
    """a 是否严格新于 b（updatedAt 字符串比较即时间序）"""
    return (a.get('updatedAt') or '') > (b.get('updatedAt') or '')


def merge_snapshots(snap_a, snap_b):
    """合并两份快照；updatedAt 相等时保留 snap_a 侧（调用方约定传服务端快照）"""
    out = {}
    for t in TABLES:
        merged, index = [], {}
        for r in snap_a.get(t, []):
            index[r['guid']] = len(merged)
            merged.append(r)
        for rb in snap_b.get(t, []):
            i = index.get(rb['guid'])
            if i is None:
                index[rb['guid']] = len(merged)
                merged.append(rb)
            elif _later(rb, merged[i]):
                merged[i] = rb  # 客户端侧更新 → 替换
        out[t] = merged

    # 墓碑并集，deletedAt 取大
    tombs = {}
    for s in (snap_a, snap_b):
        for tmb in s.get('tombstones', []):
            k = (tmb['table'], tmb['guid'])
            d = tmb.get('deletedAt') or ''
            if k not in tombs or d > tombs[k]:
                tombs[k] = d

    # 墓碑 vs 行：更新的行复活，否则墓碑胜出
    for (tbl, g), d in list(tombs.items()):
        row = next((r for r in out[tbl] if r['guid'] == g), None)
        if row is None:
            continue
        if (row.get('updatedAt') or '') > d:
            del tombs[(tbl, g)]  # 行在删除后被重建/修改 → 复活
        else:
            out[tbl].remove(row)  # 删除胜出
    out['tombstones'] = [{'table': k[0], 'guid': k[1], 'deletedAt': v} for k, v in tombs.items()]
    return out


# ---------- 应用 ----------
def _topo_order(rows):
    """tasks 按父子关系排序：父先于子插入，parent_id 一次到位；环/悬空按根处理"""
    guids = {r['guid'] for r in rows}
    placed, ordered, pending = set(), [], list(rows)
    while pending:
        rest = []
        for r in pending:
            pg = r.get('parentGuid')
            if pg and pg != r['guid'] and pg in guids and pg not in placed:
                rest.append(r)  # 父未放置，下一轮
            else:
                ordered.append(r)
                placed.add(r['guid'])
        if len(rest) == len(pending):  # 无进展 = 引用环：按根全部放下
            ordered.extend(rest)
            break
        pending = rest
    return ordered


def _fallback_project_id(conn):
    """projectGuid 解析失败时的兜底项目（理论上不发生：收集箱固定 guid 恒在）"""
    row = conn.execute("SELECT id FROM projects WHERE guid = 'p-collect' LIMIT 1").fetchone()
    if row:
        return row['id']
    row = conn.execute('SELECT id FROM projects ORDER BY id LIMIT 1').fetchone()
    return row['id'] if row else 1


def _apply_table(conn, table, rows, base_rows):
    changed = False
    # baseline 中存在但合并结果缺失 → 硬删除（同步期间新建的行不在 baseline，不受影响）
    snap_guids = {r['guid'] for r in rows}
    for g in {r['guid'] for r in base_rows} - snap_guids:
        conn.execute(f'DELETE FROM {table} WHERE guid = ?', (g,))
        changed = True

    existing = {r['guid']: (r['updated_at'] or '') for r in conn.execute(f'SELECT guid, updated_at FROM {table}')}
    # 跨表 FK 引用（folder/project）在表序保证下已就绪；同表引用（tasks.parent）需增量维护
    guid_map = {t: {r['guid']: r['id'] for r in conn.execute(f'SELECT guid, id FROM {t}')} for t in TABLES}
    cols = list(ROW_COLS[table].values()) + list(ROW_FKS.get(table, {}).keys())
    col_sql = ', '.join(['guid'] + cols + ['updated_at'])
    ph = ', '.join(['?'] * (2 + len(cols)))
    ordered = _topo_order(rows) if table == 'tasks' else rows

    for row in ordered:
        g = row['guid']
        values = [row.get(key) for key in ROW_COLS[table]]
        fk_vals = []
        for col, (key, ref) in ROW_FKS.get(table, {}).items():
            v = guid_map[ref].get(row.get(key))
            if col == 'project_id' and v is None:
                v = _fallback_project_id(conn)  # tasks.project_id NOT NULL，兜底收集箱
            fk_vals.append(v)
        params = [g] + values + fk_vals + [row.get('updatedAt')]
        cur_updated = existing.get(g)
        if cur_updated is None:
            cur = conn.execute(f'INSERT INTO {table} ({col_sql}) VALUES ({ph})', params)
            guid_map[table][g] = cur.lastrowid  # 供后续子任务解析 parent_id
            changed = True
        elif cur_updated < (row.get('updatedAt') or ''):
            conn.execute(
                f"UPDATE {table} SET {', '.join(c + ' = ?' for c in cols + ['updated_at'])} WHERE guid = ?",
                values + fk_vals + [row.get('updatedAt'), g],
            )
            changed = True
    return changed


def apply_snapshot(conn, snap, baseline):
    """把合并快照幂等应用到当前库（单事务原子应用）

    :param baseline: 应用前该库的快照（判定删除范围：仅删 baseline 中存在而快照缺失的 guid）
    :return: 是否发生了实际写入（供前端决定是否刷新数据）
    """
    changed = False
    conn.execute('BEGIN IMMEDIATE')
    try:
        # 表序保证 FK 目标先行：folders → projects → tasks（拓扑序）→ countdowns
        for t in TABLES:
            changed |= _apply_table(conn, t, snap.get(t, []), baseline.get(t, []))

        for tmb in snap.get('tombstones', []):
            if tmb['table'] in TABLES:
                conn.execute(
                    'INSERT OR REPLACE INTO _sync_tombstones (table_name, guid, deleted_at) VALUES (?,?,?)',
                    (tmb['table'], tmb['guid'], tmb.get('deletedAt') or ''),
                )
        cutoff = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(time.time() - TOMBSTONE_RETAIN_DAYS * 86400))
        conn.execute('DELETE FROM _sync_tombstones WHERE deleted_at < ?', (cutoff,))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    return changed
