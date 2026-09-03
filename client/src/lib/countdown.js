import { Lunar } from 'lunar-javascript';

const DAY = 86400000;

export function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** 下一次农历 M-D（从今天起，含今天；除夕等月末节日自动回退到该月最后一天） */
export function nextLunarDate(month, day, from) {
  const today = startOfDay(from);
  for (let y = today.getFullYear(); y <= today.getFullYear() + 1; y++) {
    let d = day;
    let solar = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        solar = Lunar.fromYmd(y, month, d).getSolar();
        break;
      } catch {
        d--; // 该月没有这么多天（如除夕 12-30 在 29 天月）
      }
    }
    if (!solar) continue;
    const date = new Date(solar.getYear(), solar.getMonth() - 1, solar.getDay());
    if (date >= today) return date;
  }
  return null;
}

/** 下一次公历 M-D（每年重复） */
export function nextSolarDate(month, day, from) {
  const today = startOfDay(from);
  let y = today.getFullYear();
  let date = new Date(y, month - 1, day);
  if (date < today) {
    y++;
    date = new Date(y, month - 1, day);
  }
  return date;
}

/**
 * 计算展示数据
 * - anniversary 纪念日：从 date 到今天的经过时间（X年Y月Z天），direction=elapsed
 * - countdown  倒数日：今天到 date 的剩余天数
 * - birthday/festival：下一次出现（农历/公历）的剩余天数
 */
export function computeCountdown(cd, now = new Date()) {
  const [y, m, d] = (cd.date || '2000-01-01').split('-').map(Number);
  const today = startOfDay(now);

  if (cd.type === 'anniversary') {
    const anchor = new Date(y, (m || 1) - 1, d || 1);
    return elapsedBreakdown(anchor, now);
  }

  let target = null;
  let label = '';
  if (cd.isLunar) {
    target = nextLunarDate(m, d, now);
    label = `农历${m}月${d}日`;
  } else if (cd.repeatYearly && cd.type !== 'countdown') {
    target = nextSolarDate(m, d, now);
    label = `${m}月${d}日`;
  } else {
    target = new Date(y, (m || 1) - 1, d || 1);
    label = `${y}年${m}月${d}日`;
  }

  const days = Math.round((startOfDay(target) - today) / DAY);
  return {
    dir: days >= 0 ? 'future' : 'past',
    days: Math.abs(days),
    targetDate: target,
    targetLabel: label,
    fmt: days === 0 ? '就是今天' : (days > 0 ? '还有' : '已经'),
  };
}

/** 纪念日经过时间：X年Y月Z天 */
export function elapsedBreakdown(anchor, now) {
  let years = now.getFullYear() - anchor.getFullYear();
  let months = now.getMonth() - anchor.getMonth();
  let days = now.getDate() - anchor.getDate();
  if (days < 0) {
    months--;
    const prevMonth = new Date(now.getFullYear(), now.getMonth(), 0).getDate();
    days += prevMonth;
  }
  if (months < 0) {
    years--;
    months += 12;
  }
  const totalDays = Math.floor((startOfDay(now) - startOfDay(anchor)) / DAY);
  return { dir: totalDays < 0 ? 'future' : 'past', years, months, days, fmt: totalDays < 0 ? '还有' : '已经', targetLabel: '' };
}
