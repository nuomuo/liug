"""官方节假日数据（口径 1:1 对应原 Node 版 server/holidays.js）

国务院办公厅公布的节假日安排（含调休补班），三个公开数据源按优先级回退，任一成功即可：
  1. NateScarlet/holiday-cn（jsdelivr CDN，数据整理自 gov.cn 通知原文）
  2. NateScarlet/holiday-cn（GitHub raw）
  3. timor.tech 节假日 API

统一输出格式：
  { year: 2026, source: 'xxx', days: { '2026-01-01': { isOff: True, name: '元旦' }, ... } }
  isOff 为 False 的日期即调休补班日。
"""
import asyncio
import re
import time

import httpx

FETCH_TIMEOUT = 8  # 秒（对齐 Node AbortSignal.timeout(8000)）
DATA_TTL = 7 * 24 * 3600 * 1000  # 已公布年份：缓存 7 天
EMPTY_TTL = 24 * 3600 * 1000  # 未公布年份（空数据）：缓存 1 天后自动重试

_cache = {}  # year -> (data, fetched_at_ms)
_inflight = {}  # year -> asyncio.Task（并发去重）


def _parse_holiday_cn(payload):
    """NateScarlet/holiday-cn：{ year, papers, days: [{ name, date, isOffDay }] }；未公布的年份 days 为空数组"""
    if not payload or not isinstance(payload.get('days'), list):
        return None
    days = {}
    for d in payload['days']:
        if not isinstance(d, dict) or not isinstance(d.get('date'), str) or not isinstance(d.get('isOffDay'), bool):
            continue
        days[d['date']] = {'isOff': d['isOffDay'], 'name': d['name'] if isinstance(d.get('name'), str) else ''}
    return days


def _parse_timor(payload):
    """timor.tech：{ code: 0, holiday: { '01-01': { holiday: True, name, date, ... } } }"""
    if not payload or payload.get('code') != 0 or not isinstance(payload.get('holiday'), dict):
        return None
    days = {}
    for v in payload['holiday'].values():
        if not isinstance(v, dict) or not isinstance(v.get('holiday'), bool):
            continue
        if not isinstance(v.get('date'), str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', v['date']):
            continue
        days[v['date']] = {'isOff': v['holiday'], 'name': v['name'] if isinstance(v.get('name'), str) else ''}
    return days


_SOURCES = [
    {'name': 'holiday-cn@jsdelivr', 'url': 'https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{y}.json', 'parse': _parse_holiday_cn},
    {'name': 'holiday-cn@github', 'url': 'https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{y}.json', 'parse': _parse_holiday_cn},
    {'name': 'timor.tech', 'url': 'https://timor.tech/api/holiday/year/{y}', 'parse': _parse_timor},
]


async def _fetch_year(year):
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
        for src in _SOURCES:
            parsed = None
            try:
                res = await client.get(src['url'].format(y=year))
                if res.status_code == 200:
                    parsed = src['parse'](res.json())
            except Exception:
                pass  # 网络错误 / 超时 / 数据格式异常：尝试下一个源
            if parsed:
                return {'year': year, 'source': src['name'], 'days': parsed}
    raise RuntimeError('所有节假日数据源均不可用')


async def _fetch_and_cache(year):
    try:
        data = await _fetch_year(year)
        _cache[year] = (data, int(time.time() * 1000))
        return data
    finally:
        _inflight.pop(year, None)


async def get_holidays(year):
    """获取某一年的官方节假日安排（内存缓存 + 并发去重）"""
    hit = _cache.get(year)
    if hit:
        data, fetched_at = hit
        ttl = DATA_TTL if data['days'] else EMPTY_TTL
        if int(time.time() * 1000) - fetched_at < ttl:
            return data
    task = _inflight.get(year)
    if task is None:
        task = asyncio.ensure_future(_fetch_and_cache(year))
        _inflight[year] = task
    return await task
