<script setup>
import { computed, ref } from 'vue';
import { store, getProject, toggleTask, taskTimeLabel, parseLocal, openTaskDetail, allTags } from '../store.js';
import Icon from './Icon.vue';
import GlassSelect from './GlassSelect.vue';
import DatePicker from './DatePicker.vue';

// 筛选条件
const selectedList = ref(0); // 清单类型：0 = 全部
const selectedTag = ref(''); // 标签：'' = 全部
const rangeStart = ref(''); // 时间范围起始日期 YYYY-MM-DD，空 = 不限
const rangeEnd = ref(''); // 时间范围结束日期 YYYY-MM-DD，空 = 不限
const statusFilter = ref('active'); // 任务状态：active=未完成 all=全部 done=已完成
const priorityFilter = ref(''); // 优先级：''=全部 5=高 3=中 1=低 0=无

const lists = computed(() => [{ id: 0, name: '全部', emoji: '' }, ...store.projects]);
const listOptions = computed(() => lists.value.map((l) => ({ value: l.id, label: (l.emoji ? l.emoji + ' ' : '') + l.name })));
const tagOptions = computed(() => [{ value: '', label: '全部' }, ...allTags.value.map((t) => ({ value: t, label: '#' + t }))]);
const statusOptions = [
  { value: 'active', label: '未完成' },
  { value: 'all', label: '全部' },
  { value: 'done', label: '已完成' },
];
const priorityOptions = [
  { value: '', label: '全部' },
  { value: '5', label: '高', dot: '#e13e39' },
  { value: '3', label: '中', dot: '#faa80c' },
  { value: '1', label: '低', dot: '#4772fa' },
  { value: '0', label: '无', dot: 'var(--grey-30)' },
];

function inTimeRange(t) {
  if (!rangeStart.value && !rangeEnd.value) return true;
  if (!t.dueDate) return false;
  const d = t.dueDate.slice(0, 10);
  if (rangeStart.value && d < rangeStart.value) return false;
  if (rangeEnd.value && d > rangeEnd.value) return false;
  return true;
}

const tasks = computed(() =>
  store.tasks
    .filter((t) => t.status !== -1)
    .filter((t) => (selectedList.value === 0 ? true : t.projectId === selectedList.value))
    .filter((t) => (selectedTag.value ? t.tags.includes(selectedTag.value) : true))
    .filter(inTimeRange)
    .filter((t) => {
      if (statusFilter.value === 'active') return t.status !== 2;
      if (statusFilter.value === 'done') return t.status === 2;
      return true;
    })
    .filter((t) => (priorityFilter.value === '' ? true : (t.priority || 0) === Number(priorityFilter.value)))
    .sort((a, b) => {
      // 已完成任务沉底，按完成时间倒序（最近完成在前）
      const aDone = a.status === 2 ? 1 : 0;
      const bDone = b.status === 2 ? 1 : 0;
      if (aDone !== bDone) return aDone - bDone;
      if (aDone) {
        const ac = a.completedAt || '';
        const bc = b.completedAt || '';
        if (ac !== bc) return ac < bc ? 1 : -1;
      }
      const ad = a.dueDate || '9999';
      const bd = b.dueDate || '9999';
      if (ad !== bd) return ad < bd ? -1 : 1;
      return (a.sortOrder || 0) - (b.sortOrder || 0);
    })
);

const hasFilter = computed(
  () =>
    selectedList.value !== 0 ||
    selectedTag.value !== '' ||
    rangeStart.value !== '' ||
    rangeEnd.value !== '' ||
    statusFilter.value !== 'active' ||
    priorityFilter.value !== ''
);
function resetFilters() {
  selectedList.value = 0;
  selectedTag.value = '';
  rangeStart.value = '';
  rangeEnd.value = '';
  statusFilter.value = 'active';
  priorityFilter.value = '';
}

function fmtDue(t) {
  if (!t.dueDate) return '';
  const d = parseLocal(t.dueDate);
  const today = new Date();
  const diff = Math.round(
    (new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000
  );
  let label = `${d.getMonth() + 1}月${d.getDate()}日`;
  if (diff === 0) label = '今天';
  else if (diff === 1) label = '明天';
  else if (diff === -1) label = '昨天';
  else if (diff < 0) label += '（已过期）';
  return label + (t.isAllDay ? '' : ' ' + taskTimeLabel(t));
}
function isOverdue(t) {
  if (!t.dueDate || t.status === 2) return false;
  return parseLocal(t.dueDate) < new Date() || t.dueDate.slice(0, 10) < new Date().toISOString().slice(0, 10);
}
function priColor(p) {
  return p === 5 ? '#e13e39' : p === 3 ? '#faa80c' : p === 1 ? '#4772fa' : 'var(--grey-60)';
}
</script>

<template>
  <div class="list-page">
    <aside class="lp-side">
      <div class="lp-filter">
        <span class="lp-filter-label">清单类型</span>
        <GlassSelect v-model="selectedList" :options="listOptions" />
      </div>
      <div class="lp-filter">
        <span class="lp-filter-label">标签</span>
        <GlassSelect v-model="selectedTag" :options="tagOptions" />
      </div>
      <div class="lp-filter">
        <span class="lp-filter-label">时间范围</span>
        <DatePicker v-model="rangeStart" style="width: 112px" />
        <span class="lp-range-sep">至</span>
        <DatePicker v-model="rangeEnd" style="width: 112px" />
      </div>
      <div class="lp-filter">
        <span class="lp-filter-label">任务状态</span>
        <GlassSelect v-model="statusFilter" :options="statusOptions" />
      </div>
      <div class="lp-filter">
        <span class="lp-filter-label">优先级</span>
        <GlassSelect v-model="priorityFilter" :options="priorityOptions" />
      </div>
      <button v-if="hasFilter" class="lp-reset" @click="resetFilters">重置</button>
    </aside>

    <main class="lp-main">
      <div class="lp-header">
        <div class="lp-title">
          {{ lists.find((l) => l.id === selectedList)?.name }}
          <span class="lp-total">{{ tasks.length }}</span>
        </div>
        <div class="lp-actions">
          <button class="lp-add" @click="store.quickAdd = { open: true, presetDate: new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()), presetTask: null }">
            <Icon name="add-small" :size="16" /> 添加任务
          </button>
        </div>
      </div>

      <div class="lp-list">
        <div v-for="t in tasks" :key="t.id" class="lp-item" @click="openTaskDetail(t, $event.clientX, $event.clientY)">
          <span class="lp-check" :style="{ color: t.status === 2 ? 'var(--grey-20)' : priColor(t.priority) }" @click.stop="toggleTask(t)">
            <Icon :name="t.status === 2 ? 'calendar-complete' : 'calendar-checkbox'" :size="20" />
          </span>
          <div class="lp-item-main">
            <div class="lp-item-title" :class="{ done: t.status === 2 }">{{ t.title }}</div>
            <div class="lp-item-sub">
              <span class="lp-item-list">{{ getProject(t.projectId)?.emoji }} {{ getProject(t.projectId)?.name }}</span>
              <span v-if="t.dueDate" class="lp-item-date" :class="{ overdue: isOverdue(t) }">{{ fmtDue(t) }}</span>
              <span v-if="t.repeatFlag" class="lp-item-repeat"><Icon name="calendar-repeat" :size="12" /></span>
              <span v-for="tag in t.tags" :key="tag" class="lp-item-tag">#{{ tag }}</span>
            </div>
          </div>
        </div>
        <div v-if="!tasks.length" class="lp-empty">
          <Icon name="calendar-sidebar" :size="44" />
          <p>{{ hasFilter ? '没有符合条件的任务' : '这里空空如也，添加一个任务吧' }}</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.list-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 10px;
  gap: 10px;
}
.lp-side {
  flex: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  padding: 10px 16px;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
}
.lp-filter {
  display: flex;
  align-items: center;
  gap: 6px;
}
.lp-filter-label {
  font-size: 12px;
  color: var(--grey-40);
  white-space: nowrap;
}
.lp-range-sep {
  font-size: 12px;
  color: var(--grey-40);
}
.lp-reset {
  margin-left: auto;
  height: 26px;
  padding: 0 12px;
  border: 1px solid var(--glass-border-soft);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  color: var(--grey-60);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s var(--ease-spring);
}
.lp-reset:hover {
  color: var(--warn-red);
  border-color: var(--warn-red);
  background: rgba(255, 255, 255, 0.7);
}
.lp-main {
  flex: 1;
  min-height: 0;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.lp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 8px;
  flex: none;
}
.lp-title {
  font-size: 20px;
  font-weight: 600;
}
.lp-total {
  font-size: 13px;
  color: var(--grey-30);
  margin-left: 6px;
  font-weight: 400;
}
.lp-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.lp-add {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--glass-border-soft);
  border-radius: 999px;
  font-size: 13px;
  color: var(--grey-80);
  background: rgba(255, 255, 255, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
  transition: all 0.2s var(--ease-spring);
}
.lp-add:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.7);
}
.lp-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 20px;
}
.lp-item {
  display: flex;
  gap: 10px;
  padding: 9px 8px;
  border-radius: var(--radius-control);
  cursor: pointer;
  border-bottom: 1px solid var(--grey-3);
  transition: background 0.2s var(--ease-spring);
}
.lp-item:hover {
  background: rgba(255, 255, 255, 0.45);
}
.lp-check {
  margin-top: 1px;
}
.lp-item-main {
  flex: 1;
  min-width: 0;
}
.lp-item-title {
  font-size: 15px;
  color: var(--front-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lp-item-title.done {
  color: var(--grey-40);
  text-decoration: line-through;
}
.lp-item-sub {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 3px;
  font-size: 12px;
  color: var(--grey-40);
}
.lp-item-date.overdue {
  color: var(--warn-red);
}
.lp-item-repeat {
  display: inline-flex;
}
.lp-item-tag {
  color: var(--primary-color);
}
.lp-empty {
  text-align: center;
  color: var(--grey-30);
  padding: 60px 0;
}
.lp-empty .icon {
  opacity: 0.35;
}
.lp-empty p {
  margin-top: 12px;
  font-size: 13px;
}
</style>
