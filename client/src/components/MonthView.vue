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
import { dayInfo, weekNumber, monthGridDates, WEEKDAY_LABELS } from '../lib/lunar.js';
import Icon from './Icon.vue';
import TaskChip from './TaskChip.vue';

const emit = defineEmits(['open-task']);

const todayStr = computed(() => store.todayStr); // 响应式：跨天自动前进（勿用启动时快照）

const grid = computed(() => monthGridDates(store.currentDate.getFullYear(), store.currentDate.getMonth()));

// 6 行 × 7 列
const rows = computed(() => {
  const out = [];
  for (let r = 0; r < 6; r++) out.push(grid.value.slice(r * 7, r * 7 + 7));
  return out;
});

/**
 * 任务按「行」（一周 7 天）分层：
 * - 跨天任务渲染为一条连续 chip（colspan 跨格，复刻原版表格实现）
 * - 同层不重叠（区间贪心分层）
 */
function rowEvents(row) {
  const weekStart = fmtDate(row[0]);
  const weekEnd = fmtDate(row[6]);
  const events = [];
  for (const t of store.tasks) {
    if (t.status === -1 || !t.startDate || !calendarVisible(t)) continue;
    if (!store.calendarSettings.showCompleted && t.status === 2) continue;
    const s = t.startDate.slice(0, 10);
    const e = (t.dueDate || t.startDate).slice(0, 10);
    if (e < weekStart || s > weekEnd) continue;
    const si = s <= weekStart ? 0 : Math.max(0, row.findIndex((d) => fmtDate(d) >= s));
    const ei = e >= weekEnd ? 6 : Math.min(6, Math.max(si, row.findIndex((d) => fmtDate(d) >= e)));
    events.push({ task: t, si, ei });
  }
  // 排序：靠左优先、长任务优先、未完成优先
  events.sort((a, b) => {
    if (a.si !== b.si) return a.si - b.si;
    if (b.ei !== a.ei) return b.ei - a.ei;
    const aDone = a.task.status === 2 ? 1 : 0;
    const bDone = b.task.status === 2 ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;
    const at = a.task.isAllDay ? 1 : 0;
    const bt = b.task.isAllDay ? 1 : 0;
    if (at !== bt) return at - bt;
    if (at === 0) {
      const ax = (a.task.startDate || '').slice(11, 16);
      const bx = (b.task.startDate || '').slice(11, 16);
      if (ax !== bx) return ax < bx ? -1 : 1;
    }
    return (a.task.sortOrder || 0) - (b.task.sortOrder || 0);
  });
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

// 每格可显示的 chip 数量（按行高动态计算，超出的折叠为「还有 N 个」）
const rowsEl = ref(null);
const rowHeight = ref(120);
const cellWidth = ref(150);
let ro = null;
onMounted(() => {
  ro = new ResizeObserver(() => {
    if (rowsEl.value && rowsEl.value.firstElementChild) {
      rowHeight.value = rowsEl.value.firstElementChild.getBoundingClientRect().height;
    }
    if (rowsEl.value) {
      cellWidth.value = rowsEl.value.getBoundingClientRect().width / 7;
    }
  });
  if (rowsEl.value) ro.observe(rowsEl.value);
});
onBeforeUnmount(() => ro && ro.disconnect());

const chipsPerCell = computed(() => Math.max(1, Math.floor((rowHeight.value - 44) / 20)));

function rowVisibleLanes(row) {
  return rowEvents(row).slice(0, chipsPerCell.value);
}
function rowHiddenCount(row) {
  const total = rowEvents(row).reduce((n, lane) => n + lane.length, 0);
  const shown = rowVisibleLanes(row).reduce((n, lane) => n + lane.length, 0);
  return total - shown;
}

// 展开某行全部任务
const expandedRow = ref(null);
const popoverLanes = computed(() => (expandedRow.value ? rowEvents(expandedRow.value) : []));
const popoverTitle = computed(() => {
  if (!expandedRow.value) return '';
  const d = expandedRow.value[0];
  return `${d.getMonth() + 1}月${d.getDate()}日 - ${expandedRow.value[6].getMonth() + 1}月${expandedRow.value[6].getDate()}日`;
});
function expandRow(row) {
  expandedRow.value = row;
}

function openQuickAdd(d) {
  store.quickAdd = { open: true, presetDate: new Date(d), presetTask: null };
}

/** 单击日期空白处直接弹出创建任务窗口（点数字仍为选中日期） */
function onTitleCellClick(e, d) {
  if (e.target.closest('.c-solar')) return;
  openQuickAdd(d);
}
function onRowBlankClick(e, row) {
  // 任务条/更多入口/标题行由各自处理器接管
  if (e.target.closest('.c-task') || e.target.closest('.more-tasks') || e.target.closest('thead')) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const col = Math.min(6, Math.max(0, Math.floor((e.clientX - rect.left) / (rect.width / 7))));
  openQuickAdd(row[col]);
}

// ---------- 拖拽：把任务移到其他日期 ----------
function onRowDragOver(e) {
  if (taskDrag.id != null) {
    e.currentTarget.classList.add('drop-target');
    e.dataTransfer.dropEffect = 'move';
  }
}
function onRowDragLeave(e) {
  e.currentTarget.classList.remove('drop-target');
}
async function onRowDrop(e, row) {
  e.currentTarget.classList.remove('drop-target');
  const id = Number(e.dataTransfer.getData('text/plain') || taskDrag.id);
  taskDrag.id = null;
  if (!id) return;
  const task = store.tasks.find((t) => t.id === id);
  if (!task) return;
  // 按鼠标 x 落点换算目标列 → 目标日
  const rect = e.currentTarget.getBoundingClientRect();
  const col = Math.min(6, Math.max(0, Math.floor((e.clientX - rect.left) / (rect.width / 7))));
  const target = fmtDate(row[col]);
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
</script>

<template>
  <div class="month-grid">
    <div class="c-day-labels">
      <div class="labels-inner">
        <div v-for="(w, i) in WEEKDAY_LABELS" :key="i" class="c-day-label" :class="{ 'c-day-weekend': i >= 5 }">
          {{ w }}
        </div>
      </div>
    </div>

    <div class="c-scroll-container" ref="rowsEl">
      <div
        v-for="(row, ri) in rows"
        :key="ri"
        class="c-row"
        @dragover.prevent="onRowDragOver"
        @dragleave="onRowDragLeave"
        @drop.prevent="onRowDrop($event, row)"
        @click="onRowBlankClick($event, row)"
      >
        <!-- 复刻原版：同一表格 thead 定义 7 列宽，tbody 用 colspan 跨天渲染连续任务条 -->
        <table class="c-events-table">
          <thead>
            <tr>
              <th
                v-for="(d, ci) in row"
                :key="fmtDate(d)"
                class="c-title-cell"
                :class="{ 'c-weekend-col': (ci >= 5 && !dayInfo(d).isWork) || dayInfo(d).isHoliday }"
                @click="onTitleCellClick($event, d)"
              >
                <div class="c-title">
                  <span class="c-solar" :class="{ today: fmtDate(d) === todayStr }" @click="store.currentDate = d">
                    {{ d.getDate() }}
                    <span v-if="dayInfo(d).isHoliday" class="c-hw-info"><Icon name="calendar-holiday" :size="11" /></span>
                    <span v-else-if="dayInfo(d).isWork" class="c-hw-info c-hw-work" title="调休补班">班</span>
                  </span>
                  <span class="c-lunar" :class="{ 'text-green': !!dayInfo(d).festival }">
                    <template v-if="d.getDate() === 1 && ri > 0">{{ d.getMonth() + 1 }}月{{ d.getDate() }}日</template>
                    <template v-else>{{ dayInfo(d).festival || dayInfo(d).label }}</template>
                  </span>
                  <span v-if="ci === 0" class="c-week-num">第 {{ weekNumber(d) }} 周</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(lane, li) in rowVisibleLanes(row)" :key="li">
              <template v-for="(ev, i) in lane" :key="ev.task.id + ri">
                <!-- 空 td 占位，保证任务从正确的列开始（复刻原版对齐方式） -->
                <td
                  v-if="i === 0 ? ev.si > 0 : ev.si > lane[i - 1].ei + 1"
                  :colspan="i === 0 ? ev.si : ev.si - lane[i - 1].ei - 1"
                  class="c-ev-cell c-ev-empty"
                ></td>
                <td :colspan="ev.ei - ev.si + 1" class="c-ev-cell">
                  <TaskChip
                    :task="ev.task"
                    :resizable="true"
                    :day-width="cellWidth"
                    @click="(t, e) => emit('open-task', t, e)"
                    @toggle="toggleTask(ev.task)"
                  />
                </td>
              </template>
            </tr>
          </tbody>
        </table>
        <div v-if="rowHiddenCount(row) > 0" class="more-tasks" @click.stop="expandRow(row)">
          还有 {{ rowHiddenCount(row) }} 个任务…
        </div>
      </div>
    </div>

    <!-- 展开某行全部任务 -->
    <div v-if="expandedRow" class="popup-cover" @click="expandedRow = null">
      <div class="day-popover" @click.stop>
        <div class="day-popover-title">{{ popoverTitle }}</div>
        <div class="day-popover-list">
          <template v-for="(lane, li) in popoverLanes" :key="li">
            <div v-for="ev in lane" :key="ev.task.id" class="popover-item">
              <TaskChip
                :task="ev.task"
                style="margin-bottom: 4px"
                @click="(t, e) => { emit('open-task', t, e); expandedRow = null; }"
                @toggle="toggleTask(ev.task)"
              />
            </div>
          </template>
          <div v-if="!popoverLanes.length" class="empty-day">这一周没有任务</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.month-grid {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}
.c-day-labels {
  height: 32px;
  flex: none;
  border-bottom: 1px solid var(--grey-5);
}
.labels-inner {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}
.c-day-label {
  font-size: 12px;
  color: var(--grey-40);
  line-height: 32px;
  text-align: center;
}

.c-scroll-container {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.c-row {
  position: relative;
  flex: 1 1 0;
  min-height: 78px;
  border-bottom: 1px solid var(--grey-5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.c-row.drop-target {
  background: var(--grey-5);
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--primary-color) 30%, transparent);
}

.c-events-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}
.c-ev-cell {
  padding: 2px 1px 0 1px;
  vertical-align: top;
  border-right: 1px solid var(--grey-5);
}
.c-ev-cell:last-child {
  border-right: none;
}

.c-title-cell {
  padding: 2px 4px 2px 2px;
  border-right: 1px solid var(--grey-5);
  border-bottom: 1px solid var(--grey-5);
  overflow: hidden;
  text-align: left;
  font-weight: normal;
}
.c-title-cell:last-child {
  border-right: none;
}
.c-weekend-col {
  background: var(--grey-1);
}
.c-title {
  display: flex;
  align-items: center;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  line-height: 24px;
}
.c-solar {
  position: relative;
  min-width: 24px;
  height: 24px;
  font-size: 13px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  flex: none;
}
.c-solar.today {
  background: var(--primary-color);
  color: #fff;
  font-weight: 600;
}
.c-hw-info {
  position: absolute;
  right: -2px;
  top: -1px;
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
.c-solar.today .c-hw-info {
  color: #fff;
  background: var(--primary-color);
}
.c-hw-info.c-hw-work {
  color: var(--grey-40);
  font-size: 9px;
}
.c-lunar {
  margin-left: 4px;
  font-size: 12px;
  color: var(--grey-40);
  overflow: hidden;
  text-overflow: ellipsis;
}
.c-week-num {
  margin-left: auto;
  font-size: 12px;
  color: var(--grey-30);
  padding-right: 4px;
  flex: none;
}

.c-events-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}
.more-tasks {
  font-size: 12px;
  color: var(--grey-40);
  padding: 1px 4px;
  cursor: pointer;
  line-height: 16px;
}
.more-tasks:hover {
  color: var(--primary-color);
}

.day-popover {
  position: absolute;
  z-index: 1300;
  left: 50%;
  top: 20%;
  transform: translateX(-50%);
  width: 380px;
  max-height: 60%;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  padding: 14px;
  display: flex;
  flex-direction: column;
  animation: day-pop-in 0.22s var(--ease-spring);
}
@keyframes day-pop-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-8px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: translateX(-50%); filter: blur(0); }
}
.day-popover-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}
.day-popover-list {
  overflow-y: auto;
}
.popover-item {
  margin-bottom: 4px;
}
.empty-day {
  color: var(--grey-40);
  font-size: 13px;
  padding: 8px 0;
}
</style>
