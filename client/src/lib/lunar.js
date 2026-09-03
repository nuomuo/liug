import { Solar } from 'lunar-javascript';
import { reactive } from 'vue';
import { api } from '../api.js';

const solarFestMap = {
  '1-1': '元旦节',
  '2-14': '情人节',
  '3-8': '妇女节',
  '3-12': '植树节',
  '4-1': '愚人节',
  '5-1': '劳动节',
  '5-4': '青年节',
  '6-1': '儿童节',
  '7-1': '建党节',
  '8-1': '建军节',
  '9-10': '教师节',
  '10-1': '国庆节',
  '10-31': '万圣夜',
  '11-1': '万圣节',
  '12-24': '平安夜',
  '12-25': '圣诞节',
};
const lunarFestMap = {
  '1-1': '春节',
  '1-2': '大年初二',
  '1-15': '元宵节',
  '2-2': '龙抬头',
  '3-3': '上巳节',
  '5-5': '端午节',
  '7-7': '七夕节',
  '7-15': '中元节',
  '8-15': '中秋节',
  '9-9': '重阳节',
  '12-8': '腊八节',
  '12-23': '小年',
};
// 法定节假日（兜底角标标识，不含调休数据；官方数据加载成功后由其覆盖）
const statutoryHolidays = new Set(['1-1', '5-1', '10-1', '10-2', '10-3', '10-4', '10-5', '10-6', '10-7']);
const lunarStatutory = new Set(['1-1', '5-5', '8-15']);

// ---------- 官方节假日数据（国务院办公厅安排，含调休补班） ----------
// 'YYYY-MM-DD' -> { isOff: boolean, name: string }；isOff=false 即调休补班日
const officialHolidays = {};
// 响应式版本号：数据加载完成后 +1，模板中调用过 dayInfo 的组件会自动重新渲染
const holidayState = reactive({ version: 0 });
// 每个会话内每个年份只请求一次；失败后隔一段时间允许重试
const requestedYears = new Map(); // year -> { status: 'loading' | 'ok' | 'fail', at }
const RETRY_AFTER = 5 * 60 * 1000;

async function loadHolidayYear(year) {
  let data;
  try {
    data = await api.getHolidays(year);
  } catch (e) {
    requestedYears.set(year, { status: 'fail', at: Date.now() });
    return;
  }
  for (const [date, v] of Object.entries(data.days || {})) {
    officialHolidays[date] = v;
  }
  requestedYears.set(year, { status: 'ok' });
  holidayState.version++; // 失效 memo 并触发依赖 dayInfo 的组件重渲染
}

function ensureHolidayYear(year) {
  const rec = requestedYears.get(year);
  if (rec) {
    if (rec.status === 'fail' && Date.now() - rec.at > RETRY_AFTER) requestedYears.delete(year);
    else return;
  }
  requestedYears.set(year, { status: 'loading' });
  loadHolidayYear(year);
}

function ymd(date) {
  const p = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

const memo = new Map();

/**
 * 某天的展示信息：农历日文本、节日/节气、是否节假日、是否调休补班
 * dida 规则：优先显示 节气/节日；月初显示农历月名；初一显示月名
 */
export function dayInfo(date) {
  // 读取响应式版本号（模板调用时建立依赖，官方数据到达后自动重渲染）
  const version = holidayState.version;
  const key = `${version}:${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  if (memo.has(key)) return memo.get(key);

  // 懒加载：首次遇到某年日期时自动请求该年官方节假日安排
  ensureHolidayYear(date.getFullYear());

  const solar = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate());
  const lunar = solar.getLunar();
  const smd = `${solar.getMonth()}-${solar.getDay()}`;
  const lmd = `${lunar.getMonth()}-${lunar.getDay()}`;

  let label = lunar.getDayInChinese();
  if (lunar.getDay() === 1) label = (lunar.getMonth() < 0 ? '闰' : '') + lunar.getMonthInChinese() + '月';
  let festival = solarFestMap[smd] || lunarFestMap[lmd] || '';
  if (!festival) {
    // 节气（仅当天显示；表值为对应 Solar 日期字符串）
    const table = lunar.getJieQiTable();
    for (const name of Object.keys(table)) {
      if (String(table[name]) === solar.toYmd()) {
        festival = name;
        break;
      }
    }
  }
  // 官方数据优先（含调休连休日与补班日）；无数据时回退到静态法定节假日表
  const off = officialHolidays[ymd(date)];
  const isHoliday = off ? off.isOff : statutoryHolidays.has(smd) || lunarStatutory.has(lmd);
  const isWork = !!off && !off.isOff; // 调休补班日（多在周末）

  const info = {
    label, // 农历文本（默认）
    festival, // 节气或节日名，优先展示
    isHoliday,
    isWork,
    isToday: false,
  };
  memo.set(key, info);
  return info;
}

/** ISO 周数（周一为一周开始） */
export function weekNumber(date) {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayNum = (d.getDay() + 6) % 7; // 周一=0
  d.setDate(d.getDate() - dayNum + 3); // 本周四
  const firstThursday = new Date(d.getFullYear(), 0, 4);
  const fdayNum = (firstThursday.getDay() + 6) % 7;
  firstThursday.setDate(firstThursday.getDate() - fdayNum + 3);
  return 1 + Math.round((d - firstThursday) / (7 * 86400000));
}

/** 周一为起始的当周数组 */
export function weekDates(date) {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayNum = (d.getDay() + 6) % 7;
  const monday = new Date(d);
  monday.setDate(d.getDate() - dayNum);
  const out = [];
  for (let i = 0; i < 7; i++) {
    const x = new Date(monday);
    x.setDate(monday.getDate() + i);
    out.push(x);
  }
  return out;
}

/** 月视图网格：覆盖指定月份的 6 周（周一起始） */
export function monthGridDates(year, month) {
  const first = new Date(year, month, 1);
  const grids = weekDates(first);
  if (grids.length < 42) {
    // 滴答显示 5~6 行，固定补足 6 行保持布局稳定
    while (grids.length < 42) {
      const last = grids[grids.length - 1];
      const x = new Date(last);
      x.setDate(last.getDate() + 1);
      grids.push(x);
    }
  }
  return grids.slice(0, 42);
}

export const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];
