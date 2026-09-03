<script setup>
import { computed, ref, watch } from 'vue';
import { store, fmtDate } from '../store.js';
import { dayInfo, WEEKDAY_LABELS } from '../lib/lunar.js';
import Icon from './Icon.vue';

const emit = defineEmits(['select']);

const todayStr = fmtDate(new Date());

// 迷你日历独立游标（原版：跟随主视图，点击标题切换年月）
const viewDate = ref(new Date(store.currentDate));
watch(
  () => store.currentDate,
  (d) => {
    viewDate.value = new Date(d);
    openMenu.value = false;
  }
);

const title = computed(() => `${viewDate.value.getFullYear()}年${viewDate.value.getMonth() + 1}月`);

const cells = computed(() => {
  const y = viewDate.value.getFullYear();
  const m = viewDate.value.getMonth();
  const first = new Date(y, m, 1);
  const lead = (first.getDay() + 6) % 7; // 周一=0
  const start = new Date(y, m, 1 - lead);
  const out = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    out.push(d);
  }
  return out;
});

// 某天是否有可见任务（小圆点提示）
function hasTask(d) {
  const ymd = fmtDate(d);
  return store.tasks.some(
    (t) => t.status === 0 && t.startDate && ymd >= t.startDate.slice(0, 10) && ymd <= (t.dueDate || t.startDate).slice(0, 10)
  );
}

const selectedStr = computed(() => fmtDate(store.currentDate));

function prevMonth() {
  const d = new Date(viewDate.value);
  d.setMonth(d.getMonth() - 1);
  viewDate.value = d;
}
function nextMonth() {
  const d = new Date(viewDate.value);
  d.setMonth(d.getMonth() + 1);
  viewDate.value = d;
}
function goToday() {
  store.currentDate = new Date();
}
function pickDay(d) {
  store.currentDate = d;
  emit('select', d);
}

// 年/月选择菜单
const openMenu = ref(false);
const years = computed(() => {
  const y = viewDate.value.getFullYear();
  return [y - 1, y, y + 1];
});
function pickMonth(m) {
  const d = new Date(viewDate.value.getFullYear(), m, 1);
  viewDate.value = d;
  openMenu.value = false;
}
function pickYear(y) {
  const d = new Date(y, viewDate.value.getMonth(), 1);
  viewDate.value = d;
}
</script>

<template>
  <div class="calendar-min-cal">
    <div class="k-calendar">
      <div class="k-title">
        <div class="k-caption">
          <div class="nav-selector">
            <span class="nav-toggle" @click="openMenu = !openMenu">
              <span class="nav-toggle-text">{{ title }}</span>
              <Icon name="down-arrow" :size="12" style="margin-left: 2px" />
            </span>

            <div v-if="openMenu" class="nav-menu" @click.stop>
              <ul class="year">
                <li v-for="y in years" :key="y" :class="{ active: y === viewDate.getFullYear() }">
                  <a class="year-change" @click="pickYear(y)">{{ y }}</a>
                </li>
              </ul>
              <ul class="month">
                <li
                  v-for="m in 12"
                  :key="m"
                  :class="{
                    active: m - 1 === viewDate.getMonth(),
                    'month-current': m - 1 === new Date().getMonth() && viewDate.getFullYear() === new Date().getFullYear(),
                  }"
                >
                  <span class="month-change" @click="pickMonth(m - 1)">{{ m }}月</span>
                </li>
              </ul>
            </div>
          </div>

          <div class="nav-btns">
            <a class="k-btn" title="上个月" @click="prevMonth"><Icon name="kalendae-chevron-left" :size="14" /></a>
            <a class="k-btn today-btn" title="今天" @click="goToday"><span class="today-dot"></span></a>
            <a class="k-btn" title="下个月" @click="nextMonth"><Icon name="kalendae-chevron-right" :size="14" /></a>
          </div>
        </div>
      </div>

      <div class="k-header">
        <span v-for="(w, i) in WEEKDAY_LABELS" :key="i" class="k-week" :class="{ 'k-weekend': i >= 5 }">{{ w }}</span>
      </div>

      <div class="k-days">
        <div v-for="(row, ri) in Math.ceil(cells.length / 7)" :key="ri" class="k-days-row">
          <span v-for="d in cells.slice(ri * 7, ri * 7 + 7)" :key="fmtDate(d)" class="k-cell m-[1px]">
            <span
              class="k-day"
              :class="{
                'k-out-of-month': d.getMonth() !== viewDate.getMonth(),
                'k-selected': fmtDate(d) === selectedStr,
                'k-today': fmtDate(d) === todayStr,
              }"
              @click="pickDay(d)"
            >
              <span class="day-circle">
                <span class="days-info-number">{{ d.getDate() }}</span>
                <span v-if="dayInfo(d).isHoliday" class="holiday-flag" title="节假日">
                  <Icon name="calendar-holiday" :size="10" />
                </span>
                <span v-else-if="dayInfo(d).isWork" class="holiday-flag work-flag" title="调休补班">班</span>
              </span>
              <i class="lunar-label">{{ dayInfo(d).festival || dayInfo(d).label }}</i>
              <span class="has-task-tips" :class="{ visible: hasTask(d) }"></span>
            </span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar-min-cal {
  padding: 9px;
  user-select: none;
}
.k-calendar {
  position: relative;
  margin: 0 auto;
  width: 232px;
}
.k-title {
  height: 30px;
  line-height: 30px;
  margin-bottom: 4px;
}
.k-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
}
.nav-selector {
  position: relative;
  flex: 1;
}
.nav-toggle {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  cursor: default;
  border-radius: 6px;
  padding: 2px 4px;
}
.nav-toggle:hover {
  background: var(--grey-4);
}
.nav-toggle-text :deep(.nav-toggle-text) {
  font-size: 14px;
}
.nav-toggle > span:first-child {
  font-size: 14px;
  line-height: 20px;
  color: var(--front-color);
}
.nav-toggle .icon {
  color: var(--grey-40);
}

.nav-menu {
  position: absolute;
  top: 30px;
  left: 0;
  z-index: 120;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  padding: 10px 12px;
  width: 218px;
  animation: nav-menu-in 0.2s var(--ease-spring);
}
@keyframes nav-menu-in {
  from { opacity: 0; transform: translateY(-5px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.nav-menu .year {
  display: flex;
  height: 24px;
  line-height: 24px;
  font-size: 12px;
  margin-bottom: 4px;
}
.nav-menu .year li {
  flex: 1;
  text-align: center;
}
.year-change {
  display: block;
  text-align: center;
  line-height: 20px;
  font-size: 14px;
  color: var(--grey-80);
  border-radius: 6px;
  cursor: pointer;
}
.year li.active .year-change {
  color: var(--primary-color);
  font-weight: 600;
}
.nav-menu .month {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px 10px;
}
.month-change {
  display: block;
  border-radius: 50%;
  text-align: center;
  font-size: 13px;
  width: 34px;
  height: 34px;
  line-height: 34px;
  cursor: pointer;
  margin: 0 auto;
}
.month-change:hover {
  background: var(--grey-5);
}
.month li.active .month-change {
  background: var(--primary-color);
  color: #fff;
}
.month li.month-current:not(.active) .month-change {
  color: var(--primary-color);
}

.nav-btns {
  display: flex;
  align-items: center;
  height: 20px;
}
.k-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 20px;
  border-radius: 5px;
  cursor: pointer;
  color: var(--grey-60);
}
.k-btn:hover {
  background: var(--grey-5);
  color: var(--front-color);
}
.k-btn + .k-btn {
  margin-left: 4px;
}
.today-btn .today-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid currentColor;
  display: block;
}

.k-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.k-week {
  width: 30px;
  text-align: center;
  line-height: 30px;
  color: var(--grey-40);
}
.k-weekend {
  color: var(--grey-30);
}

.k-days-row {
  display: flex;
  justify-content: space-between;
}
.k-cell {
  width: 30px;
  height: 40px;
  margin: 1px;
}
.k-day {
  position: relative;
  display: block;
  width: 30px;
  height: 40px;
  text-align: center;
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
}
.k-day:hover {
  background: var(--grey-5);
}
.k-out-of-month .days-info-number {
  opacity: 0.4;
}
.day-circle {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  margin: 0 auto;
  border-radius: 50%;
}
.days-info-number {
  position: relative;
  display: block;
  font-weight: 400;
  line-height: 26px;
}
/* 农历/节日直接展示在阳历日期下方（常显） */
.lunar-label {
  display: block;
  font-style: normal;
  font-size: 9px;
  line-height: 12px;
  color: var(--grey-40);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.holiday-flag {
  position: absolute;
  right: -3px;
  top: -2px;
  width: 12px;
  height: 12px;
  line-height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--green);
  background: rgba(255, 255, 255, 0.85);
  border-radius: 50%;
}
.k-today .day-circle {
  color: var(--primary-color);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--primary-color);
}
.k-selected .day-circle {
  background: var(--primary-color);
  color: #fff;
}
.k-selected .holiday-flag {
  color: #fff;
  background: var(--primary-color);
}
.holiday-flag.work-flag {
  color: var(--grey-40);
  font-size: 9px;
}
.k-selected .days-info-number {
  opacity: 1;
}
.k-selected .lunar-label {
  color: var(--grey-60);
}
.has-task-tips {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--primary-color);
  visibility: hidden;
}
.has-task-tips.visible {
  visibility: visible;
}
.k-selected .has-task-tips {
  background: #fff;
}
</style>
