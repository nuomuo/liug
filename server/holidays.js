// 官方节假日数据（国务院办公厅公布的节假日安排，含调休补班信息）
// 三个公开数据源按优先级回退，任一成功即可：
//   1. NateScarlet/holiday-cn（jsdelivr CDN，数据整理自 gov.cn 通知原文）
//   2. NateScarlet/holiday-cn（GitHub raw）
//   3. timor.tech 节假日 API
//
// 统一输出格式：
//   { year: 2026, source: 'xxx', days: { '2026-01-01': { isOff: true, name: '元旦' }, ... } }
//   isOff 为 false 的日期即调休补班日。

const FETCH_TIMEOUT = 8000;
const DATA_TTL = 7 * 24 * 3600 * 1000; // 已公布年份：缓存 7 天
const EMPTY_TTL = 24 * 3600 * 1000; // 未公布年份（空数据）：缓存 1 天后自动重试

const cache = new Map(); // year -> { data, fetchedAt }
const inflight = new Map(); // year -> Promise（并发去重）

// ---------- 各数据源解析 ----------

// NateScarlet/holiday-cn：{ year, papers, days: [{ name, date, isOffDay }] }
// 未公布的年份返回占位文件（days 为空数组）
function parseHolidayCn(json) {
  if (!json || !Array.isArray(json.days)) return null;
  const days = {};
  for (const d of json.days) {
    if (!d || typeof d.date !== 'string' || typeof d.isOffDay !== 'boolean') continue;
    days[d.date] = { isOff: d.isOffDay, name: typeof d.name === 'string' ? d.name : '' };
  }
  return days;
}

// timor.tech：{ code: 0, holiday: { '01-01': { holiday: true, name, date, ... } } }
// 未公布的年份 code 为 0 且 holiday 为空对象
function parseTimor(json) {
  if (!json || json.code !== 0 || !json.holiday || typeof json.holiday !== 'object') return null;
  const days = {};
  for (const v of Object.values(json.holiday)) {
    if (!v || typeof v.holiday !== 'boolean') continue;
    if (typeof v.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v.date)) continue;
    days[v.date] = { isOff: v.holiday, name: typeof v.name === 'string' ? v.name : '' };
  }
  return days;
}

const SOURCES = [
  {
    name: 'holiday-cn@jsdelivr',
    url: (y) => `https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/${y}.json`,
    parse: parseHolidayCn,
  },
  {
    name: 'holiday-cn@github',
    url: (y) => `https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/${y}.json`,
    parse: parseHolidayCn,
  },
  {
    name: 'timor.tech',
    url: (y) => `https://timor.tech/api/holiday/year/${y}`,
    parse: parseTimor,
  },
];

async function fetchYear(year) {
  for (const src of SOURCES) {
    let parsed = null;
    try {
      const res = await fetch(src.url(year), { signal: AbortSignal.timeout(FETCH_TIMEOUT) });
      if (res.ok) parsed = src.parse(await res.json());
    } catch {
      // 网络错误 / 超时 / 数据格式异常：尝试下一个源
    }
    if (parsed) return { year, source: src.name, days: parsed };
  }
  throw new Error('所有节假日数据源均不可用');
}

/**
 * 获取某一年的官方节假日安排（内存缓存 + 并发去重）
 * @returns {Promise<{year:number, source:string, days:Object}>}
 */
export function getHolidays(year) {
  const hit = cache.get(year);
  if (hit) {
    const ttl = Object.keys(hit.data.days).length > 0 ? DATA_TTL : EMPTY_TTL;
    if (Date.now() - hit.fetchedAt < ttl) return Promise.resolve(hit.data);
  }
  if (inflight.has(year)) return inflight.get(year);

  const p = fetchYear(year)
    .then((data) => {
      cache.set(year, { data, fetchedAt: Date.now() });
      inflight.delete(year);
      return data;
    })
    .catch((e) => {
      inflight.delete(year);
      throw e;
    });
  inflight.set(year, p);
  return p;
}
