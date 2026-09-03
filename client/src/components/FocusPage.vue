<script setup>
import { ref, computed, onBeforeUnmount } from 'vue';
import { store, toggleTask } from '../store.js';
import Icon from './Icon.vue';

const FOCUS_TOTAL = 25 * 60; // 25 分钟
const BREAK_TOTAL = 5 * 60;

const mode = ref('focus'); // focus | break
const remaining = ref(FOCUS_TOTAL);
const running = ref(false);
let timer = null;

const todayTasks = computed(() =>
  store.tasks.filter((t) => {
    if (t.status !== 0 || !t.dueDate) return false;
    const today = new Date().toISOString().slice(0, 10);
    return t.dueDate.slice(0, 10) <= today;
  })
);
const currentTaskId = ref(null);
const currentTask = computed(() => store.tasks.find((t) => t.id === currentTaskId.value));

function start() {
  if (running.value) return;
  running.value = true;
  timer = setInterval(() => {
    remaining.value--;
    if (remaining.value <= 0) {
      stop();
      if (mode.value === 'focus') {
        mode.value = 'break';
        remaining.value = BREAK_TOTAL;
        new Notification('专注结束', { body: '休息 5 分钟 ☕' });
      } else {
        mode.value = 'focus';
        remaining.value = FOCUS_TOTAL;
        new Notification('休息结束', { body: '开始下一轮专注 💪' });
      }
    }
  }, 1000);
}
function stop() {
  running.value = false;
  clearInterval(timer);
}
function reset() {
  stop();
  remaining.value = mode.value === 'focus' ? FOCUS_TOTAL : BREAK_TOTAL;
}
function switchMode(m) {
  stop();
  mode.value = m;
  remaining.value = m === 'focus' ? FOCUS_TOTAL : BREAK_TOTAL;
}
function pickTask(t) {
  currentTaskId.value = t.id;
}
function doneCurrent() {
  if (currentTask.value) toggleTask(currentTask.value);
  currentTaskId.value = null;
}

const mmss = computed(() => {
  const m = Math.floor(remaining.value / 60);
  const s = remaining.value % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
});
const progress = computed(() =>
  1 - remaining.value / (mode.value === 'focus' ? FOCUS_TOTAL : BREAK_TOTAL)
);
onBeforeUnmount(stop);
</script>

<template>
  <div class="focus-page" :class="{ breaking: mode === 'break' }">
    <div class="fp-panel">
      <div class="fp-modes">
        <button :class="{ active: mode === 'focus' }" @click="switchMode('focus')">专注</button>
        <button :class="{ active: mode === 'break' }" @click="switchMode('break')">休息</button>
      </div>

      <div class="fp-clock">
        <svg viewBox="0 0 400 400" class="fp-ring">
          <circle cx="200" cy="200" r="170" stroke-width="14" fill="none" stroke="color-mix(in srgb, var(--primary-color) 12%, transparent)" />
          <circle
            cx="200" cy="200" r="170" stroke-width="14" fill="none"
            stroke="var(--primary-color)" stroke-linecap="round"
            :stroke-dasharray="2 * Math.PI * 170"
            :stroke-dashoffset="2 * Math.PI * 170 * (1 - progress)"
            transform="rotate(-90 200 200)"
            style="transition: stroke-dashoffset 1s linear"
          />
          <circle cx="200" cy="200" r="150" class="fp-ring-inner" />
        </svg>
        <div class="fp-time">{{ mmss }}</div>
      </div>

      <div class="fp-controls">
        <button class="fp-main-btn" @click="running ? stop() : start()">
          {{ running ? '暂停' : remaining === (mode === 'focus' ? FOCUS_TOTAL : BREAK_TOTAL) ? '开始专注' : '继续' }}
        </button>
        <button class="fp-reset" @click="reset">重置</button>
      </div>

      <div class="fp-task">
        <template v-if="currentTask">
          <span class="fp-task-check" @click="doneCurrent">
            <Icon name="calendar-checkbox" :size="18" />
          </span>
          <span class="fp-task-title">{{ currentTask.title }}</span>
          <span class="fp-task-clear" @click="currentTaskId = null"><Icon name="close" :size="12" /></span>
        </template>
        <template v-else>
          <div class="fp-pick-title">选择一个今日任务开始专注：</div>
          <div class="fp-pick-list">
            <div v-for="t in todayTasks.slice(0, 6)" :key="t.id" class="fp-pick-item" @click="pickTask(t)">
              {{ t.title }}
            </div>
            <div v-if="!todayTasks.length" class="fp-pick-empty">今天没有待办任务</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.focus-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  /* 卡片底色 = 白色玻璃混入少量主题色，跟随主题变化 */
  --fp-card: color-mix(in srgb, var(--primary-color) 6%, rgba(255, 255, 255, 0.55));
}
.fp-panel {
  width: 480px;
  max-width: 94vw;
  background: var(--fp-card);
  -webkit-backdrop-filter: blur(24px) saturate(170%);
  backdrop-filter: blur(24px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  padding: 28px 32px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: background 0.3s;
}
.fp-ring-inner {
  fill: var(--fp-card);
  stroke: rgba(255, 255, 255, 0.5);
  stroke-width: 1;
}
/* 模式切换：胶囊分段控件 */
.fp-modes {
  display: flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.4);
  margin-bottom: 20px;
}
.fp-modes button {
  padding: 6px 22px;
  font-size: 14px;
  border-radius: 999px;
  color: var(--grey-60);
  transition: all 0.18s var(--ease-spring);
}
.fp-modes button:hover {
  color: var(--front-color);
}
.fp-modes button.active {
  background: var(--primary-color);
  color: #fff;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary-color) 35%, transparent);
}
.fp-clock {
  position: relative;
  width: 240px;
  height: 240px;
}
.fp-ring {
  width: 100%;
  height: 100%;
  display: block;
  filter: drop-shadow(0 4px 12px color-mix(in srgb, var(--primary-color) 18%, transparent));
}
.fp-time {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 44px;
  font-weight: 600;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
}
.fp-controls {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 18px 0 6px;
}
.fp-main-btn {
  height: 42px;
  padding: 0 36px;
  border-radius: 999px;
  background: var(--primary-color);
  color: #fff;
  font-size: 15px;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--primary-color) 40%, transparent);
  transition: all 0.18s var(--ease-spring);
}
.fp-main-btn:hover {
  background: var(--primary-hover-color);
  transform: translateY(-1px);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--primary-color) 45%, transparent);
}
.fp-reset {
  height: 42px;
  padding: 0 22px;
  border-radius: 999px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  background: rgba(255, 255, 255, 0.55);
  color: var(--grey-80);
  font-size: 14px;
  transition: all 0.18s var(--ease-spring);
}
.fp-reset:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.8);
}
.fp-task {
  margin-top: 12px;
  width: 100%;
  text-align: center;
}
.fp-task-title {
  font-size: 16px;
  font-weight: 500;
}
.fp-task-check, .fp-task-clear {
  cursor: pointer;
  color: var(--grey-60);
  vertical-align: middle;
  border-radius: 6px;
  padding: 2px;
  transition: background 0.15s var(--ease-spring), color 0.15s var(--ease-spring);
}
.fp-task-check:hover {
  color: var(--green);
  background: rgba(29, 29, 31, 0.05);
}
.fp-task-clear {
  margin-left: 8px;
  color: var(--grey-40);
}
.fp-task-clear:hover {
  color: var(--grey-80);
  background: rgba(29, 29, 31, 0.05);
}
.fp-pick-title {
  font-size: 13px;
  color: var(--grey-40);
  margin-bottom: 8px;
}
.fp-pick-list {
  max-height: 150px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.fp-pick-item {
  max-width: 100%;
  padding: 7px 16px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  background: rgba(255, 255, 255, 0.45);
  font-size: 14px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: all 0.15s var(--ease-spring);
}
.fp-pick-item:hover {
  background: rgba(255, 255, 255, 0.75);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(20, 20, 40, 0.08);
}
.fp-pick-empty {
  font-size: 13px;
  color: var(--grey-30);
  padding: 10px;
}
</style>
