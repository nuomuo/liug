<script setup>
import { computed, ref } from 'vue';
import { store, getProject, toggleTask, taskTimeLabel, parseLocal, openTaskDetail } from '../store.js';
import Icon from './Icon.vue';

// 清单选择
const selectedList = ref(0); // 0 = 全部
const lists = computed(() => [{ id: 0, name: '全部', emoji: '' }, ...store.projects]);
const showDone = ref(false);

const tasks = computed(() =>
  store.tasks
    .filter((t) => t.status !== -1)
    .filter((t) => (selectedList.value === 0 ? true : t.projectId === selectedList.value))
    .filter((t) => (showDone.value ? true : t.status !== 2))
    .sort((a, b) => {
      const ad = a.dueDate || '9999';
      const bd = b.dueDate || '9999';
      if (ad !== bd) return ad < bd ? -1 : 1;
      return (a.sortOrder || 0) - (b.sortOrder || 0);
    })
);

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
      <div class="lp-side-title">清单</div>
      <div
        v-for="l in lists"
        :key="l.id"
        class="lp-side-item"
        :class="{ active: selectedList === l.id }"
        @click="selectedList = l.id"
      >
        <span v-if="l.emoji" class="lp-emoji">{{ l.emoji }}</span>
        <Icon v-else name="inbox-list" :size="16" style="margin-right: 6px" />
        <span class="lp-name">{{ l.name }}</span>
        <span class="lp-count">
          {{ l.id === 0 ? store.tasks.filter((t) => t.status === 0).length : store.tasks.filter((t) => t.projectId === l.id && t.status === 0).length }}
        </span>
      </div>
    </aside>

    <main class="lp-main">
      <div class="lp-header">
        <div class="lp-title">
          {{ lists.find((l) => l.id === selectedList)?.name }}
          <span class="lp-total">{{ tasks.length }}</span>
        </div>
        <div class="lp-actions">
          <label class="lp-toggle">
            <input v-model="showDone" type="checkbox" />
            显示已完成
          </label>
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
          <p>这里空空如也，添加一个任务吧</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.list-page {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 6px 6px 6px 0;
  gap: 0;
}
.lp-side {
  width: 220px;
  flex: none;
  background: var(--main-background-color);
  border-radius: 10px 0 0 10px;
  padding: 12px 8px;
  overflow-y: auto;
}
.lp-side-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--grey-40);
  padding: 0 10px 8px;
}
.lp-side-item {
  display: flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--grey-80);
  font-size: 14px;
}
.lp-side-item:hover {
  background: var(--grey-4);
}
.lp-side-item.active {
  background: var(--grey-8);
  color: var(--front-color);
  font-weight: 500;
}
.lp-emoji {
  margin-right: 6px;
}
.lp-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lp-count {
  font-size: 12px;
  color: var(--grey-30);
}
.lp-main {
  flex: 1;
  min-width: 0;
  background: var(--main-background-color);
  border-radius: 0 10px 10px 0;
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
.lp-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--grey-60);
  cursor: pointer;
}
.lp-add {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--grey-20);
  border-radius: 8px;
  font-size: 13px;
  color: var(--grey-80);
}
.lp-add:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
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
  border-radius: 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--grey-3);
}
.lp-item:hover {
  background: var(--grey-3);
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
