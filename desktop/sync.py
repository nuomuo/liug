"""桌面端云端同步引擎（仅 desktop/main.py 组装时注册；小组件内嵌模式不注册，避免双引擎）

- 触发：登录云端账号后初始拉取、本地数据变更后防抖、定时（5 分钟）、手动 /api/sync/run
- 流程：本地镜像快照 → POST {remoteUrl}/api/sync（携带远程令牌）→ 服务端 LWW 合并并应用
  → 客户端把合并结果 verbatim 应用回本地镜像库（两端收敛到同一状态）
- 状态：<data>/sync-state.json 持久化 lastSyncAt / lastChangedAt / lastError；
  GET /api/sync/status 供前端轮询（lastChangedAt 变化 → 前端刷新数据）
- 断网：同步失败仅记录状态（'offline'），本地镜像照常使用，恢复后自动补同步；
  远程令牌过期（'expired'）：提示重新登录，不影响离线使用
"""
import json
import threading
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends

from core.db import open_database_at_path, user_db_ctx, user_db_path
from core.errors import ApiError
from core.sync import apply_snapshot, build_snapshot
from local_auth import LOCAL_UID, SESSION_COOKIE, get_user_id, load_remote_session

DEBOUNCE_SECONDS = 3      # 变更后防抖：等连环写结束再同步
INTERVAL_SECONDS = 300    # 定时同步间隔
SYNC_TIMEOUT = 60.0

router = APIRouter(prefix='/api')


class SyncEngine:
    def __init__(self, data_dir):
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()       # 串行化同步（自动 / 手动互斥）
        self._event = threading.Event()     # 变更信号（防抖由 worker 消化）
        self._stop = threading.Event()
        self._state = self._load_state()

    # ---------- 状态持久化 ----------
    def _state_file(self):
        return self._data_dir / 'sync-state.json'

    def _load_state(self):
        try:
            d = json.loads(self._state_file().read_text(encoding='utf-8'))
            if isinstance(d, dict):
                return {'lastSyncAt': int(d.get('lastSyncAt') or 0),
                        'lastChangedAt': int(d.get('lastChangedAt') or 0),
                        'lastError': str(d.get('lastError') or ''),
                        'errorKind': str(d.get('errorKind') or '')}
        except Exception:
            pass
        return {'lastSyncAt': 0, 'lastChangedAt': 0, 'lastError': '', 'errorKind': ''}

    def _save_state(self):
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._state_file().write_text(json.dumps(self._state, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    # ---------- 对外接口 ----------
    def status(self):
        rs = load_remote_session()
        return {
            'enabled': bool(rs),
            'remoteUrl': rs['remoteUrl'] if rs else '',
            'lastSyncAt': self._state['lastSyncAt'],
            'lastChangedAt': self._state['lastChangedAt'],
            'lastError': self._state['lastError'],
            'errorKind': self._state['errorKind'],
        }

    def notify_change(self):
        """数据变更信号（前端 kick / 登录初始拉取）：唤醒 worker 防抖同步"""
        self._event.set()

    def run_now(self):
        """手动同步（阻塞至完成）；返回状态字典"""
        self._sync_once()
        return self.status()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name='cloud-sync').start()

    def stop(self):
        self._stop.set()
        self._event.set()

    # ---------- 内部 ----------
    def _run(self):
        while not self._stop.is_set():
            # 等待变更信号（立即唤醒）或定时超时；stop() 同时 set 两个事件以打断等待
            if self._event.wait(timeout=INTERVAL_SECONDS):
                if self._stop.is_set():
                    break
                time.sleep(DEBOUNCE_SECONDS)  # 防抖：等连环写结束
                self._event.clear()
            self._sync_once()

    def _set_error(self, kind, message):
        self._state = {**self._state, 'lastError': message, 'errorKind': kind}
        self._save_state()

    def _sync_once(self):
        with self._lock:
            rs = load_remote_session()
            if not rs:
                return  # 单机模式 / 已登出：无需同步
            uid = rs['uid']
            try:
                # 全新镜像库：先建空库（不播种默认数据），内容完全来自本次同步
                mirror = user_db_path(uid)
                if not mirror.exists():
                    conn0 = open_database_at_path(mirror)
                    conn0.close()
                with user_db_ctx(uid, seed=False) as conn:
                    local = build_snapshot(conn)
                r = httpx.post(rs['remoteUrl'] + '/api/sync', json={'snapshot': local},
                               cookies={SESSION_COOKIE: rs['token']}, timeout=SYNC_TIMEOUT)
                if r.status_code == 401:
                    self._set_error('expired', '云端会话已过期，请重新登录')
                    return
                if r.status_code != 200:
                    self._set_error('error', f'同步失败（HTTP {r.status_code}）')
                    return
                merged = r.json().get('snapshot')
                if not isinstance(merged, dict):
                    self._set_error('error', '服务器同步响应异常')
                    return
                with user_db_ctx(uid, seed=False) as conn:
                    changed = apply_snapshot(conn, merged, local)
                now = int(time.time() * 1000)
                self._state = {
                    'lastSyncAt': now,
                    'lastChangedAt': now if changed else self._state['lastChangedAt'],
                    'lastError': '', 'errorKind': '',
                }
                self._save_state()
            except httpx.HTTPError:
                self._set_error('offline', '网络不可用，恢复后自动同步')
            except Exception as e:
                self._set_error('error', '同步失败：' + (str(e) or '未知错误'))


# ---------- 引擎单例（main.py 启动时 init；widget 内嵌模式不初始化） ----------
_engine = None


def init_engine(data_dir) -> SyncEngine:
    global _engine
    if _engine is None:
        _engine = SyncEngine(data_dir)
    return _engine


def get_engine():
    return _engine


# ---------- 路由 ----------
@router.get('/sync/status')
def sync_status():
    """同步状态（前端 30s 轮询；单机模式 enabled=false）"""
    engine = get_engine()
    if engine is None:
        return {'enabled': False, 'remoteUrl': '', 'lastSyncAt': 0, 'lastChangedAt': 0,
                'lastError': '', 'errorKind': ''}
    return engine.status()


@router.post('/sync/run')
def sync_run(uid: str = Depends(get_user_id)):
    """手动触发一次同步（阻塞至完成）"""
    if uid == LOCAL_UID:
        raise ApiError(400, '单机模式无需同步')
    engine = get_engine()
    if engine is None:
        raise ApiError(503, '同步引擎未启动')
    return engine.run_now()


@router.post('/sync/kick')
def sync_kick():
    """数据变更通知（前端每次写操作后 fire-and-forget；无需鉴权，单机模式下为空操作）"""
    engine = get_engine()
    if engine:
        engine.notify_change()
    return {'ok': True}
