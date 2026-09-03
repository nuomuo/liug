<script setup>
import { computed } from 'vue';
import { getProject, taskTimeLabel, startTaskDrag, endTaskDrag, parseLocal } from '../store.js';
import { api } from '../api.js';
import Icon from './Icon.vue';

const props = defineProps({
  task: { type: Object, required: true },
  /** 是否显示拉伸手柄（仅任务起始日的 chip） */
  resizable: { type: Boolean, default: false },
  /** 月视图单格宽度（px），用于把手柄拖动换算为天数 */
  dayWidth: { type: Number, default: 100 },
});
const emit = defineEmits(['click', 'toggle']);

const project = computed(() => getProject(props.task.projectId));
const checked = computed(() => props.task.status === 2);

// 与原版一致：背景 = 清单色（未完成 0.56 / 已完成 0.18）
const style = computed(() => {
  const color = project.value?.color || '#484553';
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  const alpha = checked.value ? 0.18 : 0.56;
  const textColor = checked.value ? 'rgba(25,25,25,0.4)' : 'rgba(25,25,25,0.8)';
  return {
    backgroundColor: `rgba(${r}, ${g}, ${b}, ${alpha})`,
    color: textColor,
  };
});

const priorityClass = computed(() => {
  switch (props.task.priority) {
    case 5: return 'priority-high';
    case 3: return 'priority-medium';
    case 1: return 'priority-low';
    default: return 'none-priority';
  }
});

// ---------- 拉伸手柄：改变任务时间范围 ----------
function shiftIso(iso, days) {
  if (!iso) return iso;
  const dt = parseLocal(iso);
  dt.setDate(dt.getDate() + days);
  const p = (n) => String(n).padStart(2, '0');
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}T${iso.slice(11)}`;
}

function onHandleDown(side, e) {
  e.preventDefault();
  e.stopPropagation();
  const startX = e.clientX;
  const snap = {
    startDate: props.task.startDate,
    dueDate: props.task.dueDate || props.task.startDate,
  };
  const move = (ev) => {
    const dd = Math.round((ev.clientX - startX) / (props.dayWidth || 100));
    if (!dd) return;
    let start = snap.startDate;
    let due = snap.dueDate;
    if (side === 'right') {
      due = shiftIso(snap.dueDate, dd);
      if (due < start) due = start;
    } else {
      start = shiftIso(snap.startDate, dd);
      if (due && due < start) due = start;
    }
    // 本地即时更新（仅内存），松手后统一提交
    props.task.startDate = start;
    props.task.dueDate = due;
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
    api
      .updateTask(props.task.id, { startDate: props.task.startDate, dueDate: props.task.dueDate })
      .catch(() => {});
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}
</script>

<template>
  <div
    class="c-task"
    :class="[priorityClass, { checked }]"
    :style="style"
    draggable="true"
    @dragstart="startTaskDrag(props.task, $event)"
    @dragend="endTaskDrag"
    @click="emit('click', props.task, $event)"
    :title="props.task.title"
  >
    <span v-if="props.resizable" class="chip-resizer left" @mousedown="onHandleDown('left', $event)"></span>
    <div class="c-task-inner">
      <span class="c-task-icon" @click.stop="emit('toggle', props.task)">
        <Icon v-if="checked" name="calendar-complete" :size="14" />
        <Icon v-else name="calendar-checkbox" :size="14" />
      </span>
      <span class="c-task-body">
        <span class="c-task-title">{{ props.task.title }}</span>
        <span v-if="taskTimeLabel(props.task)" class="c-task-time">{{ taskTimeLabel(props.task) }}</span>
      </span>
      <span v-if="props.task.repeatFlag" class="c-task-repeat"><Icon name="calendar-repeat" :size="12" /></span>
    </div>
    <span v-if="props.resizable" class="chip-resizer right" @mousedown="onHandleDown('right', $event)"></span>
  </div>
</template>

<style scoped>
.c-task {
  position: relative;
  height: 18px;
  margin: 0 3px 2px 2px;
  padding: 0 3px;
  border-radius: 3px;
  border: 1px solid transparent;
  cursor: pointer;
  overflow: visible;
  transition: opacity 0.2s;
}
.c-task:hover {
  filter: brightness(0.96);
}
.c-task-inner {
  display: flex;
  align-items: center;
  font-size: 12px;
  height: 16px;
  overflow: hidden;
}
.c-task-icon {
  flex: none;
  margin-right: 2px;
  display: inline-flex;
  align-items: center;
  color: rgba(25, 25, 25, 0.4);
}
.checked .c-task-icon {
  color: rgba(25, 25, 25, 0.25);
}
.c-task-body {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  line-height: 16px;
}
.c-task-title {
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  position: relative;
  line-height: 16px;
  flex: 1;
  min-width: 0;
}
.c-task-time {
  flex: none;
  font-size: 10px;
  line-height: 16px;
  margin-left: 4px;
  opacity: 0.75;
}
.checked .c-task-title {
  text-decoration: line-through;
  color: rgba(25, 25, 25, 0.4);
}
.c-task-repeat {
  flex: none;
  display: inline-flex;
  margin-left: 2px;
  color: rgba(25, 25, 25, 0.4);
}

/* 拉伸手柄（复刻原版 resizer：系统 ew-resize 光标） */
.chip-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 10px;
  /* 优先使用系统光标图标 */
  cursor: ew-resize;
  z-index: 12;
  opacity: 0;
  transition: opacity 0.12s;
}
.chip-resizer.left {
  left: 0;
  border-radius: 3px 0 0 3px;
}
.chip-resizer.right {
  right: 0;
  border-radius: 0 3px 3px 0;
}
.c-task:hover .chip-resizer {
  opacity: 1;
}
.chip-resizer:hover {
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 0 0 1px rgba(25, 25, 25, 0.15);
}
</style>
