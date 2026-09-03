<script setup>
import { computed, ref, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { store, showToast, loadBootstrap, openTaskDetail, placeDropdown } from '../store.js';
import { api } from '../api.js';
import MiniCalendar from './MiniCalendar.vue';
import FilterPanel from './FilterPanel.vue';
import MonthView from './MonthView.vue';
import WeekView from './WeekView.vue';
import Icon from './Icon.vue';

const emit = defineEmits(['open-task']);
function openTask(t, e) {
  openTaskDetail(t, e?.clientX ?? undefined, e?.clientY ?? undefined);
}

// 当前标题：月视图 → 2026年10月；周视图 → 9月28日 - 10月4日
const rangeTitle = computed(() => {
  const d = store.currentDate;
  if (store.calendarViewMode === 'month') {
    return `${d.getFullYear()}年${d.getMonth() + 1}月`;
  }
  const mon = new Date(d);
  mon.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const f = (x) => `${x.getMonth() + 1}月${x.getDate()}日`;
  return mon.getMonth() === sun.getMonth() ? f(sun) : `${f(mon)} - ${f(sun)}`;
});

function step(dir) {
  const d = new Date(store.currentDate);
  if (store.calendarViewMode === 'month') d.setMonth(d.getMonth() + dir);
  else d.setDate(d.getDate() + 7 * dir);
  store.currentDate = d;
}
function goToday() {
  store.currentDate = new Date();
}

// 月份下拉（在触发位置弹出）
const monthPicker = ref(null);
const pickerYear = ref(new Date().getFullYear());
const rangeTitleRef = ref(null);
const monthPickerRef = ref(null);
async function toggleMonthPicker() {
  monthPicker.value = monthPicker.value ? null : new Date(store.currentDate);
  if (monthPicker.value) {
    pickerYear.value = monthPicker.value.getFullYear();
    await nextTick();
    placeDropdown(monthPickerRef.value, rangeTitleRef.value);
  }
}
function pickMonth(m) {
  store.currentDate = new Date(pickerYear.value, m, 1);
  monthPicker.value = null;
}

// 视图切换（月/周，在触发位置弹出）
const viewMenu = ref(false);
const viewSwitchRef = ref(null);
const viewMenuRef = ref(null);
async function toggleViewMenu() {
  viewMenu.value = !viewMenu.value;
  if (viewMenu.value) {
    await nextTick();
    placeDropdown(viewMenuRef.value, viewSwitchRef.value);
  }
}
function setViewMode(mode) {
  store.calendarViewMode = mode;
  viewMenu.value = false;
}

// 更多菜单（在触发位置弹出）
const moreMenu = ref(false);
const moreBtnRef = ref(null);
const moreMenuRef = ref(null);
async function toggleMoreMenu() {
  moreMenu.value = !moreMenu.value;
  if (moreMenu.value) {
    await nextTick();
    placeDropdown(moreMenuRef.value, moreBtnRef.value, { align: 'right' });
  }
}
function toggleCompleted() {
  store.calendarSettings.showCompleted = !store.calendarSettings.showCompleted;
  moreMenu.value = false;
}
function printCalendar() {
  window.print();
  moreMenu.value = false;
}
async function importCsv() {
  moreMenu.value = false;
  const path = window.prompt('请输入备份 CSV 文件路径：', '');
  if (!path) return;
  try {
    const r = await api.importCsv(path.trim());
    await loadBootstrap();
    showToast(`导入完成：${r.projects} 个清单 / ${r.tasks} 条任务`);
  } catch (e) {
    showToast('导入失败：' + (e.data?.error || e.message));
  }
}

// 左面板（迷你日历 + 筛选）显示/隐藏，点击日历筛选图标切换（复刻原版 expendMiniCal）
const showLeftPanel = ref(true);

// 左面板宽度拖拽（复刻 detail-dragger）
const leftWidth = ref(248);
const dragging = ref(false);
function onDraggerDown() {
  dragging.value = true;
  const move = (e) => {
    leftWidth.value = Math.min(420, Math.max(200, e.clientX - 50));
  };
  const up = () => {
    dragging.value = false;
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

// 点击空白关闭浮层
function onDocClick(e) {
  if (!e.target.closest('.c-range-wrap')) monthPicker.value = null;
  if (!e.target.closest('.view-switch')) viewMenu.value = false;
  if (!e.target.closest('.more-btn')) moreMenu.value = false;
}
onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));
</script>

<template>
  <div class="calendar-page" :class="{ 'no-left': !showLeftPanel }">
    <!-- 左侧：迷你日历 + 筛选 -->
    <div v-if="showLeftPanel" class="tk-calendar-left-view" :style="{ width: leftWidth + 'px' }">
      <MiniCalendar />
      <FilterPanel />
      <div class="detail-dragger" :class="{ active: dragging }" @mousedown="onDraggerDown"></div>
    </div>

    <!-- 右侧：导航 + 视图 -->
    <div class="tk-calendar-content">
      <div class="c-nav">
        <div class="c-range-wrap">
          <div class="nav-icon-btn" title="筛选清单" @click="showLeftPanel = !showLeftPanel">
            <div class="bgIconWrapper">
              <span class="bg-hover"></span>
              <Icon name="calendar-filter" :size="24" />
            </div>
          </div>
          <div class="c-range-select headerDate">
            <h5 ref="rangeTitleRef" class="c-range-title" @click="toggleMonthPicker">
              <span class="c-range">{{ rangeTitle }}</span>
              <Icon name="small-triangle-down" :size="12" class="c-range-arrow" />
            </h5>

            <div v-if="monthPicker" ref="monthPickerRef" class="month-picker dropdown-menu" @click.stop>
              <div class="picker-year-nav">
                <a class="k-btn" @click="pickerYear--"><Icon name="chevron-left" :size="14" /></a>
                <span class="picker-year">{{ pickerYear }}年</span>
                <a class="k-btn" @click="pickerYear++"><Icon name="chevron-right" :size="14" /></a>
              </div>
              <div class="picker-months">
                <span
                  v-for="m in 12"
                  :key="m"
                  class="picker-month"
                  :class="{
                    active: monthPicker && pickerYear === store.currentDate.getFullYear() && m - 1 === store.currentDate.getMonth(),
                    current: pickerYear === new Date().getFullYear() && m - 1 === new Date().getMonth(),
                  }"
                  @click="pickMonth(m - 1)"
                >
                  {{ m }}月
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="header-right-wrapper">
          <div class="add-btn" title="添加任务" @click="store.quickAdd = { open: true, presetDate: new Date(store.currentDate.getFullYear(), store.currentDate.getMonth(), store.currentDate.getDate()), presetTask: null }">
            <Icon name="add-small" :size="16" />
          </div>

          <div ref="viewSwitchRef" class="view-switch" @click="toggleViewMenu">
            <p>{{ store.calendarViewMode === 'month' ? '月' : '周' }}</p>
            <Icon name="small-triangle-down" :size="10" />
            <div v-if="viewMenu" ref="viewMenuRef" class="dropdown-menu view-menu" @click.stop>
              <li :class="{ sel: store.calendarViewMode === 'month' }" @click="setViewMode('month')">月</li>
              <li :class="{ sel: store.calendarViewMode === 'week' }" @click="setViewMode('week')">周</li>
            </div>
          </div>

          <div class="btn-group switch-range">
            <button class="group-btn" @click="step(-1)"><Icon name="chevron-left" :size="20" /></button>
            <button class="group-btn today" @click="goToday">今天</button>
            <button class="group-btn" @click="step(1)"><Icon name="chevron-right" :size="20" /></button>
          </div>

          <div ref="moreBtnRef" class="more-btn" @click="toggleMoreMenu">
            <div class="bgIconWrapper">
              <span class="bg-hover"></span>
              <Icon name="more-titlebar" :size="20" />
            </div>
            <div v-if="moreMenu" ref="moreMenuRef" class="dropdown-menu" @click.stop>
              <li @click="toggleCompleted">
                <Icon :name="store.calendarSettings.showCompleted ? 'calendar-checkbox' : 'calendar-complete'" :size="14" />
                {{ store.calendarSettings.showCompleted ? '隐藏已完成任务' : '显示已完成任务' }}
              </li>
              <li @click="importCsv"><Icon name="add-small" :size="14" />导入 CSV 备份…</li>
              <li @click="printCalendar"><Icon name="more" :size="14" />打印日历</li>
            </div>
          </div>
        </div>
      </div>

      <div class="tkcalendar-main-container">
        <MonthView v-if="store.calendarViewMode === 'month'" @open-task="openTask" />
        <WeekView v-else @open-task="openTask" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar-page {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 10px 10px 10px 10px;
  gap: 10px;
  min-width: 0;
}
/* 左面板隐藏时：内容面板独自占满 */
.calendar-page.no-left {
  padding-left: 10px;
}

/* 左侧面板（悬浮玻璃卡） */
.tk-calendar-left-view {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: none;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  overflow: hidden;
}
.detail-dragger {
  position: absolute;
  width: 7px;
  height: 100%;
  right: -4px;
  top: 0;
  z-index: 2;
  cursor: col-resize;
}
.detail-dragger:hover,
.detail-dragger.active {
  background: color-mix(in srgb, var(--primary-color) 25%, transparent);
  border-radius: 4px;
}

/* 右侧内容（悬浮玻璃卡） */
.tk-calendar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  min-width: 0;
}

.c-nav {
  position: relative;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 56px;
  flex: none;
  padding: 12px 16px;
}
.c-range-wrap {
  display: flex;
  align-items: center;
  height: 32px;
}
.nav-icon-btn {
  margin-right: 8px;
  color: var(--grey-60);
  cursor: pointer;
}
.c-range-select {
  position: relative;
  flex: none;
  margin-right: 4px;
}
.c-range-title {
  font-size: 21px;
  line-height: 32px;
  display: inline-flex;
  align-items: center;
  position: relative;
  padding: 0 8px;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.c-range-title:hover {
  background: rgba(29, 29, 31, 0.05);
}
.c-range {
  color: var(--front-color);
}
.c-range-arrow {
  margin-left: 4px;
  color: var(--grey-40);
  opacity: 0;
}
.c-range-title:hover .c-range-arrow {
  opacity: 1;
}

.month-picker {
  width: 236px;
  padding: 12px 14px;
}
.picker-year-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.picker-year {
  font-size: 14px;
  font-weight: 600;
}
.picker-months {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
}
.picker-month {
  display: inline-block;
  width: 36px;
  height: 36px;
  line-height: 36px;
  text-align: center;
  border-radius: 50%;
  font-size: 13px;
  cursor: pointer;
  margin: 0 auto;
}
.picker-month:hover {
  background: rgba(29, 29, 31, 0.06);
}
.picker-month.current {
  color: var(--primary-color);
}
.picker-month.active {
  background: var(--primary-color);
  color: #fff;
}

.header-right-wrapper {
  display: flex;
  align-items: center;
}
.add-btn {
  width: 32px;
  height: 32px;
  margin-right: 14px;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--grey-80);
  transition: all 0.15s var(--ease-spring);
}
.add-btn:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.75);
}

.view-switch {
  position: relative;
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  margin-right: 14px;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  color: var(--grey-80);
  transition: all 0.15s var(--ease-spring);
}
.view-switch:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.75);
}
.view-switch p {
  font-size: 14px;
  margin-right: 2px;
  line-height: 30px;
}
.view-menu {
  min-width: 90px;
}
.view-menu li.sel {
  color: var(--primary-color);
  font-weight: 600;
}

.btn-group {
  display: flex;
  align-items: center;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.5);
  margin-right: 14px;
  overflow: hidden;
  height: 32px;
}
.group-btn {
  width: 36px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--grey-80);
}
.group-btn:hover {
  color: var(--primary-color);
  background: rgba(29, 29, 31, 0.04);
}
.group-btn.today {
  width: auto;
  padding: 0 14px;
  border-left: 1px solid rgba(29, 29, 31, 0.08);
  border-right: 1px solid rgba(29, 29, 31, 0.08);
  font-size: 14px;
}

.more-btn {
  position: relative;
  color: var(--grey-60);
  cursor: pointer;
}


.tkcalendar-main-container {
  position: relative;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
</style>
