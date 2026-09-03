<script setup>
import { computed, ref } from 'vue';
import { store, updateTaskLocal, getProject, openTaskDetail, toggleTask, fmtDate, parseLocal } from '../store.js';
import Icon from './Icon.vue';

const todayStr = fmtDate(new Date());

// 重要 = 中/高优先级；紧急 = 今天或已过期
function isImportant(t) {
  return t.priority >= 3;
}
function isUrgent(t) {
  return t.dueDate && t.dueDate.slice(0, 10) <= todayStr;
}

const QUADRANTS = [
  { key: 'q1', title: '重要且紧急', color: '#FF5F68', important: true, urgent: true },
  { key: 'q2', title: '重要不紧急', color: '#FFB000', important: true, urgent: false },
  { key: 'q3', title: '不重要但紧急', color: '#4772FA', important: false, urgent: true },
  { key: 'q4', title: '不重要不紧急', color: '#0CCE9C', important: false, urgent: false },
];

function quadrantOf(t) {
  const imp = isImportant(t);
  const urg = isUrgent(t);
  if (imp && urg) return 'q1';
  if (imp && !urg) return 'q2';
  if (!imp && urg) return 'q3';
  return 'q4';
}

// 象限内分组：今天 / 最近7天 / 更远 / 无日期
function sectionOf(t) {
  if (!t.dueDate) return '无日期';
  const d = t.dueDate.slice(0, 10);
  if (d <= todayStr) return '今天';
  const diff = (new Date(d + 'T00:00:00') - new Date(todayStr + 'T00:00:00')) / 86400000;
  if (diff <= 7) return '最近7天';
  return '更远';
}
const SECTION_ORDER = ['今天', '最近7天', '更远', '无日期'];

function tasksOfQuadrant(q) {
  const map = { 今天: [], 最近7天: [], 更远: [], 无日期: [] };
  for (const t of store.tasks) {
    if (t.status !== 0 || quadrantOf(t) !== q.key) continue;
    map[sectionOf(t)].push(t);
  }
  for (const k of Object.keys(map)) {
    map[k].sort((a, b) => {
      const ad = a.dueDate || '9999';
      const bd = b.dueDate || '9999';
      if (ad !== bd) return ad < bd ? -1 : 1;
      return (a.sortOrder || 0) - (b.sortOrder || 0);
    });
  }
  return SECTION_ORDER.filter((s) => map[s].length).map((s) => ({ name: s, tasks: map[s] }));
}

function priColor(p) {
  return p === 5 ? '#e13e39' : p === 3 ? '#faa80c' : p === 1 ? '#4772fa' : 'var(--grey-60)';
}

function dueLabel(t) {
  if (!t.dueDate) return '';
  const d = t.dueDate.slice(0, 10);
  if (d === todayStr) return '今天';
  const diff = (new Date(d + 'T00:00:00') - new Date(todayStr + 'T00:00:00')) / 86400000;
  if (diff === 1) return '明天';
  const dt = parseLocal(t.dueDate);
  if (!t.isAllDay) {
    const p = (n) => String(n).padStart(2, '0');
    return `${dt.getMonth() + 1}月${dt.getDate()}日 ${p(dt.getHours())}:${p(dt.getMinutes())}`;
  }
  return `${dt.getMonth() + 1}月${dt.getDate()}日`;
}
function isOverdue(t) {
  if (!t.dueDate) return false;
  return t.dueDate.slice(0, 10) < todayStr;
}

// ---------- 拖拽到象限 ----------
let dragTask = null;
const dragOverKey = ref(null);

function onTaskDragStart(e, t) {
  dragTask = t;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', String(t.id));
}
function onTaskDragEnd() {
  dragTask = null;
  dragOverKey.value = null;
}
function onQuadDragOver(e, q) {
  if (dragTask) {
    e.preventDefault();
    dragOverKey.value = q.key;
  }
}
async function onQuadDrop(e, q) {
  dragOverKey.value = null;
  const id = Number(e.dataTransfer.getData('text/plain'));
  const t = store.tasks.find((x) => x.id === id) || dragTask;
  dragTask = null;
  if (!t) return;
  if (quadrantOf(t) === q.key) return;

  const patch = { priority: q.important ? 5 : 0 };
  const p = (n) => String(n).padStart(2, '0');
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
  if (q.urgent) {
    patch.dueDate = todayIso + 'T23:59:00';
    if (!t.startDate) patch.startDate = todayIso + 'T00:00:00';
  } else {
    patch.dueDate = null;
    patch.startDate = null;
  }
  await updateTaskLocal(t, patch);
}

function openDetail(e, t) {
  openTaskDetail(t, e.clientX, e.clientY);
}

function onDblClick(q) {
  store.quickAdd = {
    open: true,
    presetDate: new Date(),
    presetTask: null,
    presetQuadrant: q,
  };
}

const total = computed(() => store.tasks.filter((t) => t.status === 0).length);
</script>

<template>
  <div class="matrix-page">
    <div class="mp-header">
      <h1 class="mp-title">四象限</h1>
      <div class="mp-hint">拖动任务到不同象限：重要 ↔ 优先级，紧急 ↔ 截止日期</div>
      <div class="mp-more">
        <div class="bgIconWrapper">
          <span class="bg-hover"></span>
          <Icon name="more-titlebar" :size="20" />
        </div>
      </div>
    </div>

    <div class="matrix-container">
      <div v-for="q in QUADRANTS" :key="q.key" class="quadrant" :class="{ 'drag-over': dragOverKey === q.key }"
        @dragover.prevent="onQuadDragOver($event, q)" @dragleave="dragOverKey === q.key && (dragOverKey = null)"
        @drop.prevent="onQuadDrop($event, q)" @dblclick="onDblClick(q)">
        <div class="quadrant-header">
          <div class="qh-left">
            <span class="qh-dot" :style="{ background: q.color }"></span>
            <h3 :style="{ color: q.color }">{{ q.title }}</h3>
          </div>
          <div class="qh-actions">
            <span class="qh-add" title="添加任务" @click="onDblClick(q)"><Icon name="add" :size="20" /></span>
          </div>
        </div>

        <div class="tasklist">
          <div v-for="sec in tasksOfQuadrant(q)" :key="sec.name" class="section">
            <div class="section-header">
              <h6 class="section-title">{{ sec.name }}</h6>
              <span class="section-count">{{ sec.tasks.length }}</span>
            </div>
            <div
              v-for="t in sec.tasks"
              :key="t.id"
              class="l-task"
              draggable="true"
              @dragstart="onTaskDragStart($event, t)"
              @dragend="onTaskDragEnd"
              @click="openDetail($event, t)"
            >
              <span class="t-check" :style="{ color: priColor(t.priority) }" @click.stop="toggleTask(t)">
                <Icon name="calendar-checkbox" :size="18" />
              </span>
              <span class="t-title">{{ t.title }}</span>
              <span class="t-tips">
                <span v-if="getProject(t.projectId)" class="t-project">
                  {{ getProject(t.projectId).emoji }}
                  <span class="t-project-name">{{ getProject(t.projectId).name }}</span>
                </span>
                <span v-if="t.dueDate" class="t-date" :class="{ overdue: isOverdue(t) }">{{ dueLabel(t) }}</span>
              </span>
            </div>
          </div>
          <div v-if="!tasksOfQuadrant(q).length" class="quadrant-empty">暂无任务，双击空白处添加</div>
        </div>
      </div>
    </div>

    <div class="mp-footer" v-if="total">共 {{ total }} 个未完成任务</div>
  </div>
</template>

<style scoped>
.matrix-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 6px 6px 6px 0;
  background: var(--main-background-color);
  border-radius: 10px;
  min-width: 0;
}
.mp-header {
  display: flex;
  align-items: center;
  padding: 10px 16px 4px;
  flex: none;
}
.mp-title {
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  margin-right: 6px;
  padding-left: 10px;
}
.mp-hint {
  font-size: 12px;
  color: var(--grey-40);
  flex: 1;
}
.mp-more {
  color: var(--grey-60);
  cursor: pointer;
}

.matrix-container {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  padding: 8px 16px 16px;
  min-height: 0;
}
.quadrant {
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--grey-5);
  transition: box-shadow 0.15s, border-color 0.15s;
}
.quadrant.drag-over {
  border-color: var(--primary-color);
  box-shadow: inset 0 0 0 2px var(--primary-color);
}
.quadrant-header {
  height: 40px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
}
.qh-left {
  display: flex;
  align-items: center;
  overflow: hidden;
  flex: 1;
}
.qh-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: none;
  margin-right: 8px;
}
.qh-left h3 {
  font-size: 13px;
  line-height: 18px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qh-actions {
  display: flex;
  align-items: center;
}
.qh-add {
  cursor: pointer;
  color: var(--grey-60);
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px;
  border-radius: 5px;
}
.qh-add:hover {
  background: var(--grey-5);
}
.quadrant:hover .qh-add {
  opacity: 1;
}

.tasklist {
  flex: 1;
  overflow-y: auto;
  padding: 0 0 6px;
}
.section-header {
  display: flex;
  align-items: baseline;
  padding: 6px 12px 2px;
  cursor: default;
}
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--grey-60);
}
.section-count {
  font-size: 12px;
  color: var(--grey-40);
  margin-left: 8px;
}

.l-task {
  display: flex;
  align-items: center;
  height: 40px;
  line-height: 40px;
  padding: 0 16px 0 12px;
  cursor: pointer;
  position: relative;
}
.l-task:hover {
  background: var(--grey-4);
}
.t-check {
  display: inline-flex;
  align-items: center;
  margin-right: 10px;
  cursor: pointer;
  flex: none;
}
.t-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.t-tips {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
  flex: none;
}
.t-project {
  font-size: 12px;
  color: var(--grey-40);
  display: inline-flex;
  align-items: center;
  max-width: 130px;
}
.t-project-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 72px;
  margin-left: 2px;
}
.t-date {
  font-size: 12px;
  color: var(--grey-40);
  white-space: nowrap;
}
.t-date.overdue {
  color: var(--warn-red);
}
.quadrant-empty {
  text-align: center;
  color: var(--grey-30);
  font-size: 12px;
  padding: 24px 0;
}
.mp-footer {
  padding: 0 16px 12px;
  font-size: 12px;
  color: var(--grey-40);
}
</style>
