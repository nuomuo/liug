<script setup>
import { ref, watch } from 'vue';
import { store, getProject, taskTimeLabel, openTaskDetail } from '../store.js';
import { api } from '../api.js';
import Icon from './Icon.vue';

const q = ref('');
const results = ref([]);
const searching = ref(false);

watch(q, async (v) => {
  if (!v.trim()) {
    results.value = [];
    return;
  }
  searching.value = true;
  try {
    const r = await api.search(v.trim());
    results.value = r.tasks;
  } finally {
    searching.value = false;
  }
});

function open(t, e) {
  openTaskDetail(t, e?.clientX, e?.clientY);
  store.searchOpen = false;
}
</script>

<template>
  <div class="search-overlay" @mousedown.self="store.searchOpen = false">
    <div class="search-panel">
      <div class="search-bar">
        <Icon name="search-sidebar" :size="18" />
        <input
          v-model="q"
          autofocus
          placeholder="搜索任务、备注、标签…"
          @keydown.escape="store.searchOpen = false"
        />
        <span v-if="q && !searching" class="search-count">{{ results.length }} 个结果</span>
      </div>
      <div class="search-results">
        <div
          v-for="t in results"
          :key="t.id"
          class="result-item"
          @click="open(t, $event)"
        >
          <span class="r-check" :style="{ color: t.status === 2 ? 'var(--grey-20)' : 'var(--grey-60)' }">
            <Icon :name="t.status === 2 ? 'calendar-complete' : 'calendar-checkbox'" :size="18" />
          </span>
          <div class="r-main">
            <div class="r-title" :class="{ done: t.status === 2 }">{{ t.title }}</div>
            <div class="r-sub">
              <span class="r-list">{{ getProject(t.projectId)?.emoji }} {{ getProject(t.projectId)?.name }}</span>
              <span v-if="t.startDate" class="r-date">{{ t.startDate.slice(0, 10) }} {{ taskTimeLabel(t) }}</span>
              <span v-for="tag in t.tags" :key="tag" class="r-tag">#{{ tag }}</span>
            </div>
          </div>
        </div>
        <div v-if="q && !results.length && !searching" class="search-empty">
          <Icon name="search-sidebar" :size="40" />
          <p>未找到与“{{ q }}”相关的任务</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-overlay {
  position: fixed;
  inset: 0;
  z-index: 1400;
  background: rgba(15, 18, 30, 0.18);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
  display: flex;
  justify-content: center;
  padding-top: 12vh;
}
.search-panel {
  width: 620px;
  max-width: 92vw;
  max-height: 62vh;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  align-self: flex-start;
  animation: search-in 0.22s var(--ease-spring);
}
@keyframes search-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); filter: blur(6px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--grey-5);
  color: var(--grey-40);
}
.search-bar input {
  flex: 1;
  height: 38px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.6);
  padding: 0 12px;
  font-size: 16px;
  color: var(--front-color);
  transition: border-color 0.15s var(--ease-spring), box-shadow 0.15s var(--ease-spring);
}
.search-bar input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 15%, transparent);
}
.search-bar input::placeholder {
  color: var(--grey-40);
}
.search-count {
  font-size: 12px;
  color: var(--grey-40);
  flex: none;
}
.search-results {
  overflow-y: auto;
  padding: 8px;
  user-select: none;
}
.result-item {
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-control);
  cursor: pointer;
  transition: background 0.15s var(--ease-spring);
}
.result-item:hover {
  background: rgba(255, 255, 255, 0.5);
}
.r-check {
  margin-top: 2px;
}
.r-main {
  min-width: 0;
  flex: 1;
}
.r-title {
  font-size: 14px;
  color: var(--front-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.r-title.done {
  color: var(--grey-40);
  text-decoration: line-through;
}
.r-sub {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--grey-40);
  margin-top: 2px;
}
.r-tag {
  color: var(--primary-color);
}
.search-empty {
  text-align: center;
  color: var(--grey-30);
  padding: 36px 0;
}
.search-empty .icon {
  opacity: 0.4;
}
.search-empty p {
  margin-top: 10px;
  font-size: 13px;
}
</style>
