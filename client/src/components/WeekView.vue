<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import {
  store,
  calendarVisible,
  toggleTask,
  updateTaskLocal,
  fmtDate,
  parseLocal,
  taskDrag,
} from '../store.js';
import { dayInfo, weekNumber, weekDates, WEEKDAY_LABELS } from '../lib/lunar.js';
import Icon from './Icon.vue';
import TaskChip from './TaskChip.vue';

const emit = defineEmits(['open-task']);

const todayStr = fmtDate(new Date());
const days = computed(() => weekDates(store.currentDate));
const hours = Array.from({ length: 24 }, (_, i) => i);

const HOURS_AREA_HEIGHT = 24 * 56;

function allDayTasks(d) {
  const ymd = fmtDate(d);
  return store.tasks.filter(
    (t) =>
      t.status !== -1 &&
      t.isAllDay &&
      ymd >= (t.startDate || '').slice(0, 10) &&
      ymd <= (t.dueDate || t.startDate || '').slice(0, 10) &&
      calendarVisible(t) &&
      (store.calendarSettings.showCompleted || t.status !== 2)
  );
}

/** 全天任务按周分层：跨天任务为一条连续 chip（colspan） */
function allDayLanes() {
  const week = days.value;
  const weekStart = fmtDate(week[0]);
  const weekEnd = fmtDate(week[6]);
  const events = [];
  for (const t of store.tasks) {
    if (t.status === -1 || !t.isAllDay || !t.startDate || !calendarVisible(t)) continue;
    if (!store.calendarSettings.showCompleted && t.status === 2) continue;
    const s = t.startDate.slice(0, 10);
    const e = (t.dueDate || t.startDate).slice(0, 10);
    if (e < weekStart || s > weekEnd) continue;
    const si = s <= weekStart ? 0 : Math.max(0, week.findIndex((d) => fmtDate(d) >= s));
    const ei = e >= weekEnd ? 6 : Math.min(6, Math.max(si, week.findIndex((d) => fmtDate(d) >= e)));
    events.push({ task: t, si, ei });
  }
  events.sort((a, b) => (a.si - b.si) || (b.ei - a.ei));
  const lanes = [];
  for (const ev of events) {
    let placed = false;
    for (const lane of lanes) {
      if (lane[lane.length - 1].ei < ev.si) {
        lane.push(ev);
        placed = true;
        break;
      }
    }
    if (!placed) lanes.push([ev]);
  }
  return lanes;
}

/** 当天有时间的任务 → 定位块 */
function timedTasks(d) {
  const ymd = fmtDate(d);
  return store.tasks
    .filter(
      (t) =>
        t.status !== -1 &&
        !t.isAllDay &&
        t.startDate &&
        t.startDate.slice(0, 10) === ymd &&
        calendarVisible(t) &&
        (store.calendarSettings.showCompleted || t.status !== 2)
    )
    .map((t) => {
      const s = parseLocal(t.startDate);
      const e = parseLocal(t.dueDate) || new Date(s.getTime() + 1800000);
      const startMin = s.getHours() * 60 + s.getMinutes();
      let endMin = e.getHours() * 60 + e.getMinutes();
      if (fmtDate(e) !== ymd) endMin = 24 * 60;
      if (endMin <= startMin) endMin = startMin + 30;
      return { task: t, startMin, endMin };
    })
    .sort((a, b) => a.startMin - b.startMin);
}

function blockStyle(item) {
  const p = store.projectsById?.[item.task.projectId];
  void p;
  const proj = store.projects.find((x) => x.id === item.task.projectId);
  const color = proj?.color || '#484553';
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  const done = item.task.status === 2;
  return {
    top: (item.startMin / 60) * 56 + 'px',
    height: Math.max(18, ((item.endMin - item.startMin) / 60) * 56 - 2) + 'px',
    backgroundColor: `rgba(${r}, ${g}, ${b}, ${done ? 0.18 : 0.82})`,
    color: done ? 'rgba(25,25,25,0.45)' : '#fff',
  };
}

function timeLabel(item) {
  const s = parseLocal(item.task.startDate);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(s.getHours())}:${p(s.getMinutes())}`;
}

// 当前时间线
const now = new Date();
const nowTop = ((now.getHours() * 60 + now.getMinutes()) / 60) * 56;

function openQuickAdd(d, hour) {
  const date = new Date(d);
  date.setHours(hour ?? 9, 0, 0, 0);
  store.quickAdd = { open: true, presetDate: date, presetTask: null };
}

// 拖拽到某天
const cellW = ref(150);
function onDragOver(e) {
  if (taskDrag.id != null) e.currentTarget.classList.add('drop-target');
}
function onDragLeave(e) {
  e.currentTarget.classList.remove('drop-target');
}

/** 全天区拖拽：按鼠标 x 落点换算目标日，整条平移（保持时长） */
async function onAlldayDrop(e) {
  e.currentTarget.classList.remove('drop-target');
  const id = Number(e.dataTransfer.getData('text/plain') || taskDrag.id);
  taskDrag.id = null;
  if (!id) return;
  const task = store.tasks.find((t) => t.id === id);
  if (!task) return;
  const rect = e.currentTarget.getBoundingClientRect();
  cellW.value = rect.width / 7;
  const col = Math.min(6, Math.max(0, Math.floor((e.clientX - rect.left) / cellW.value)));
  const target = fmtDate(days.value[col]);
  const oldStart = (task.startDate || '').slice(0, 10);
  if (oldStart === target) return;
  const offsetDays = Math.round((new Date(target + 'T00:00:00') - new Date(oldStart + 'T00:00:00')) / 86400000);
  const shift = (iso) => {
    if (!iso) return iso;
    const dt = parseLocal(iso);
    dt.setDate(dt.getDate() + offsetDays);
    const p = (n) => String(n).padStart(2, '0');
    return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}T${iso.slice(11)}`;
  };
  await updateTaskLocal(task, { startDate: shift(task.startDate), dueDate: shift(task.dueDate) });
}
async function onDrop(e, d, hour) {
  e.currentTarget.classList.remove('drop-target');
  const id = Number(e.dataTransfer.getData('text/plain') || taskDrag.id);
  taskDrag.id = null;
  if (!id) return;
  const task = store.tasks.find((t) => t.id === id);
  if (!task) return;
  const p = (n) => String(n).padStart(2, '0');
  const patch = { startDate: `${fmtDate(d)}T${p(hour ?? parseLocal(task.startDate)?.getHours() ?? 9)}:${p(parseLocal(task.startDate)?.getMinutes() ?? 0)}:00` };
  // 保持时长
  const s = parseLocal(task.startDate);
  const en = parseLocal(task.dueDate);
  if (s && en) {
    const dur = en - s;
    const ns = parseLocal(patch.startDate);
    const ne = new Date(ns.getTime() + dur);
    patch.dueDate = `${ne.getFullYear()}-${p(ne.getMonth() + 1)}-${p(ne.getDate())}T${p(ne.getHours())}:${p(ne.getMinutes())}:00`;
  } else {
    patch.dueDate = patch.startDate;
  }
  await updateTaskLocal(task, patch);
}
</script>

<template>
  <div class="week-grid">
    <!-- 表头 -->
    <div class="w-header">
      <div class="w-corner"></div>
      <div v-for="(d, i) in days" :key="i" class="w-day-col" :class="{ 'c-weekend-col': i >= 5 }">
        <div class="w-day-title" @click="store.currentDate = d">
          <span class="w-week-label">{{ WEEKDAY_LABELS[i] }}</span>
          <span class="w-day-num" :class="{ today: fmtDate(d) === todayStr }" @dblclick="openQuickAdd(d)">{{ d.getDate() }}</span>
        </div>
      </div>
    </div>

    <div class="w-body">
      <!-- 全天任务行 -->
      <div class="w-allday">
        <div class="w-corner allday-label">全天</div>
        <div
          class="w-allday-grid"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onAlldayDrop"
        >
          <table class="w-allday-table">
            <tbody>
              <tr v-for="(lane, li) in allDayLanes()" :key="li">
                <template v-for="(ev, i) in lane" :key="ev.task.id">
                  <td
                    v-if="i === 0 ? ev.si > 0 : ev.si > lane[i - 1].ei + 1"
                    :colspan="i === 0 ? ev.si : ev.si - lane[i - 1].ei - 1"
                    class="w-ev-cell w-ev-empty"
                  ></td>
                  <td :colspan="ev.ei - ev.si + 1" class="w-ev-cell">
                    <TaskChip
                      :task="ev.task"
                      :resizable="true"
                      :day-width="cellW"
                      style="margin: 0 2px 2px 2px"
                      @click="(t, e) => emit('open-task', t, e)"
                      @toggle="toggleTask(ev.task)"
                    />
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 时间网格 -->
      <div class="w-scroll">
        <div class="w-grid-inner" :style="{ height: HOURS_AREA_HEIGHT + 'px' }">
          <div class="w-hours">
            <div v-for="h in hours" :key="h" class="w-hour">{{ h > 0 ? (h < 10 ? '0' + h + ':00' : h + ':00') : '' }}</div>
          </div>
          <div
            v-for="(d, i) in days"
            :key="'t' + i"
            class="w-day-col time-col"
            :class="{ 'c-weekend-col': i >= 5, today: fmtDate(d) === todayStr }"
            @dragover.prevent="onDragOver"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop($event, d, null)"
          >
            <div
              v-for="item in timedTasks(d)"
              :key="item.task.id"
              class="w-event"
              :style="blockStyle(item)"
              @click="emit('open-task', item.task, $event)"
            >
              <div class="w-event-time">{{ timeLabel(item) }}</div>
              <div class="w-event-title">{{ item.task.title }}</div>
            </div>
            <div v-if="fmtDate(d) === todayStr" class="w-now-line" :style="{ top: nowTop + 'px' }">
              <span class="w-now-dot"></span>
            </div>
            <div v-for="h in hours" :key="h" class="w-hour-slot" @dblclick="openQuickAdd(d, h)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.week-grid {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.w-header {
  display: flex;
  flex: none;
  border-bottom: 1px solid var(--grey-5);
  height: 40px;
}
.w-corner {
  width: 50px;
  flex: none;
}
.w-day-col {
  flex: 1;
  min-width: 0;
  border-right: 1px solid var(--grey-5);
  overflow: hidden;
}
.w-day-col:last-child {
  border-right: none;
}
.c-weekend-col {
  background: rgba(29, 29, 31, 0.03);
}
.w-day-title {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 6px;
  padding-top: 6px;
  cursor: pointer;
}
.w-week-label {
  font-size: 12px;
  color: var(--grey-40);
}
.w-day-num {
  font-size: 18px;
  font-weight: 500;
  min-width: 26px;
  height: 26px;
  line-height: 26px;
  text-align: center;
  border-radius: 50%;
}
.w-day-num.today {
  background: var(--primary-color);
  color: #fff;
}

.w-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.w-allday {
  display: flex;
  flex: none;
  min-height: 28px;
  border-bottom: 1px solid var(--grey-5);
}
.allday-label {
  font-size: 11px;
  color: var(--grey-40);
  display: flex;
  align-items: center;
  justify-content: center;
}
.w-allday-grid {
  flex: 1;
  min-width: 0;
  padding: 2px 3px;
}
.w-allday-grid.drop-target {
  background: var(--grey-5);
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--primary-color) 30%, transparent);
}
.w-allday-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}
.w-ev-cell {
  padding: 0;
  vertical-align: top;
}

.w-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.w-grid-inner {
  display: flex;
  position: relative;
}
.w-hours {
  width: 50px;
  flex: none;
}
.w-hour {
  height: 56px;
  font-size: 11px;
  color: var(--grey-40);
  text-align: right;
  padding-right: 8px;
  transform: translateY(-6px);
}
.time-col {
  position: relative;
  background-image: linear-gradient(to bottom, var(--grey-5) 1px, transparent 1px);
  background-size: 100% 56px;
}
.time-col.drop-target {
  background-color: var(--grey-5);
}
.w-hour-slot {
  height: 56px;
  cursor: default;
}
.w-event {
  position: absolute;
  left: 3px;
  right: 4px;
  z-index: 2;
  border-radius: 10px;
  padding: 2px 6px;
  font-size: 12px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.3);
  -webkit-backdrop-filter: blur(4px) saturate(150%);
  backdrop-filter: blur(4px) saturate(150%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 2px 8px rgba(20, 20, 40, 0.1);
  transition: box-shadow 0.2s var(--ease-spring), transform 0.2s var(--ease-spring);
}
.w-event:hover {
  filter: brightness(1.05);
  transform: translateY(-1px);
  z-index: 3;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 4px 14px rgba(20, 20, 40, 0.16);
}
.w-event-time {
  font-size: 10px;
  opacity: 0.85;
}
.w-event-title {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.w-now-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: #e13e39;
  border-radius: 1px;
  box-shadow: 0 0 8px rgba(225, 62, 57, 0.45);
  z-index: 3;
}
.w-now-dot {
  position: absolute;
  left: -4px;
  top: -3px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e13e39;
  box-shadow: 0 0 6px rgba(225, 62, 57, 0.55);
}
</style>
