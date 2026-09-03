<script setup>
import { computed, ref } from 'vue';
import { store, allTags, showToast } from '../store.js';
import Icon from './Icon.vue';

const collapsed = ref({ list: false, tag: false, sub: true });

const allChecked = computed(() => store.selectedProjectIds.length === 0 && !store.selectedTag);

function toggleAll() {
  if (!allChecked.value) {
    store.selectedProjectIds = [];
    store.selectedTag = '';
  }
}

function toggleProject(id) {
  const idx = store.selectedProjectIds.indexOf(id);
  if (idx >= 0) store.selectedProjectIds.splice(idx, 1);
  else {
    store.selectedProjectIds.push(id);
    store.selectedTag = '';
  }
}

function toggleTag(tag) {
  store.selectedTag = store.selectedTag === tag ? '' : tag;
}

function projectCount(p) {
  return store.tasks.filter((t) => t.projectId === p.id && t.status === 0).length;
}
</script>

<template>
  <div class="filter-panel">
    <div class="filter-header" @click="toggleAll">
      <span class="filter-title">所有</span>
      <span class="mini-checkbox round" :class="{ checked: allChecked }">
        <Icon name="right-panel-all-selected" :size="9" />
      </span>
    </div>

    <div class="filter-list">
      <!-- 清单 -->
      <div class="group-header" @click="collapsed.list = !collapsed.list">
        <span class="group-label">
          <span class="collapse-arrow" :class="{ collapsed: collapsed.list }">
            <Icon name="down-arrow" :size="12" />
          </span>
          <span class="group-name">清单</span>
        </span>
        <span class="mini-checkbox" :class="{ checked: store.selectedProjectIds.length > 0 }">
          <Icon name="right-panel-all-selected" :size="9" />
        </span>
      </div>
      <template v-if="!collapsed.list">
        <li
          v-for="p in store.projects"
          :key="p.id"
          class="option-item"
          @click="toggleProject(p.id)"
        >
          <span class="option-left">
            <Icon v-if="p.emoji === '' && p.name === '收集箱'" name="inbox-list" :size="18" class="opt-icon" />
            <span v-else-if="p.emoji" class="emoji">{{ p.emoji }}</span>
            <span v-else class="color-dot" :style="{ background: p.color }"></span>
            <span class="option-name">{{ p.name }}</span>
          </span>
          <span class="mini-checkbox" :class="{ checked: store.selectedProjectIds.includes(p.id) }">
            <Icon name="right-panel-all-selected" :size="9" />
          </span>
        </li>
        <li class="option-item muted" @click="showToast('右键清单或在任务中切换清单即可管理')">
          <span class="option-left">
            <Icon name="add-small" :size="14" class="opt-icon" />
            <span class="option-name">添加清单…</span>
          </span>
        </li>
      </template>

      <!-- 标签 -->
      <div class="group-header" @click="collapsed.tag = !collapsed.tag">
        <span class="group-label">
          <span class="collapse-arrow" :class="{ collapsed: collapsed.tag }">
            <Icon name="down-arrow" :size="12" />
          </span>
          <span class="group-name">标签</span>
        </span>
        <span class="mini-checkbox" :class="{ checked: !!store.selectedTag }">
          <Icon name="right-panel-all-selected" :size="9" />
        </span>
      </div>
      <template v-if="!collapsed.tag">
        <li
          v-for="tag in allTags"
          :key="tag"
          class="option-item"
          @click="toggleTag(tag)"
        >
          <span class="option-left">
            <Icon name="tag" :size="16" class="opt-icon" />
            <span class="option-name">{{ tag }}</span>
          </span>
          <span class="mini-checkbox" :class="{ checked: store.selectedTag === tag }">
            <Icon name="right-panel-all-selected" :size="9" />
          </span>
        </li>
        <li v-if="!allTags.length" class="empty-hint">暂无标签</li>
      </template>

      <!-- 订阅日历 -->
      <div class="group-header" @click="collapsed.sub = !collapsed.sub">
        <span class="group-label">
          <span class="collapse-arrow" :class="{ collapsed: collapsed.sub }">
            <Icon name="down-arrow" :size="12" />
          </span>
          <span class="group-name">订阅日历</span>
        </span>
        <span class="mini-checkbox"><Icon name="right-panel-all-selected" :size="9" /></span>
      </div>
      <template v-if="!collapsed.sub">
        <li class="option-item muted" @click="showToast('订阅日历功能暂未开放')">
          <span class="option-left">
            <Icon name="calendar-classic" :size="16" class="opt-icon" v-if="false" />
            <span class="color-dot" style="background: var(--grey-20)"></span>
            <span class="option-name">添加订阅日历…</span>
          </span>
          <span class="mini-checkbox"><Icon name="right-panel-all-selected" :size="9" /></span>
        </li>
      </template>
    </div>
  </div>
</template>

<style scoped>
.filter-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-top: 10px;
}
.filter-header {
  height: 42px;
  padding: 10px 16px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--grey-5);
  cursor: pointer;
  flex: none;
}
.filter-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--grey-60);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-checkbox.round {
  border-radius: 50%;
}

.filter-list {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 10px;
}
.group-header {
  height: 32px;
  padding-right: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.group-header:hover .group-name {
  color: var(--grey-80);
}
.group-label {
  display: flex;
  align-items: center;
  min-width: 85%;
}
.collapse-arrow {
  padding: 0 2px;
  color: var(--grey-40);
  display: inline-flex;
  opacity: 0;
  transition: transform 0.15s;
}
.group-header:hover .collapse-arrow {
  opacity: 1;
}
.collapse-arrow.collapsed {
  transform: rotate(-90deg);
}
.group-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--grey-60);
  padding-left: 6px;
  white-space: nowrap;
}

.option-item {
  height: 32px;
  /* 左边距与「所有」标题（16px）一致，使图标列对齐在一条竖线上 */
  padding: 0 16px 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.option-item:hover {
  background: var(--grey-4);
}
.option-left {
  display: flex;
  align-items: center;
  width: 85%;
  min-width: 0;
}
.opt-icon {
  flex: none;
  color: var(--grey-60);
  margin-right: 6px;
}
.emoji {
  font-size: 16px;
  line-height: 16px;
  width: 18px;
  text-align: center;
  flex: none;
}
.color-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: none;
  margin-right: 6px;
}
.option-name {
  font-size: 13px;
  color: var(--grey-80);
  padding-left: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.option-item.muted .option-name {
  color: var(--grey-40);
}
.empty-hint {
  font-size: 12px;
  color: var(--grey-30);
  padding: 4px 16px 4px 26px;
}
</style>
