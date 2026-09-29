<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue';
import {
  store,
  getProject,
  updateTaskLocal,
  deleteTaskLocal,
  toggleTask,
  addTask,
  subtasksOf,
  closeTaskDetail,
  allTags,
  placeDropdown,
} from '../store.js';
import Icon from './Icon.vue';
import DatePicker from './DatePicker.vue';
import MarkdownEditor from './MarkdownEditor.vue';

const props = defineProps({
  task: { type: Object, required: true },
});

const title = ref(props.task.title);
// 日期弹层组件引用（切换任务时关闭）
const startPickRef = ref(null);
const endPickRef = ref(null);
watch(
  () => props.task.id,
  () => {
    title.value = props.task.title;
    newSub.value = '';
    startPickRef.value?.close();
    endPickRef.value?.close();
  }
);
watch(title, (v) => {
  if (v !== props.task.title) {
    updateTaskLocal(props.task, { title: v });
  }
});

const project = computed(() => getProject(props.task.projectId));

const priorities = [
  { value: 0, label: '无优先级', icon: 'priority-0', color: 'var(--grey-60)' },
  { value: 1, label: '低', icon: 'priority-1', color: '#4772fa' },
  { value: 3, label: '中', icon: 'priority-2', color: '#faa80c' },
  { value: 5, label: '高', icon: 'priority-3', color: '#e13e39' },
];
const activePriority = computed(() => priorities.find((p) => p.value === props.task.priority) || priorities[0]);

const openMenu = ref('');

const dateStr = computed({
  get: () => props.task.startDate?.slice(0, 10) || '',
  set: (v) => {
    const t = props.task;
    const startTime = t.isAllDay ? 'T00:00:00' : 'T' + (t.startDate?.slice(11) || '09:00:00');
    const dueTime = t.isAllDay ? 'T00:00:00' : 'T' + (t.dueDate?.slice(11) || startTime.slice(1));
    const startDay = t.startDate?.slice(0, 10);
    const dueDay = t.dueDate?.slice(0, 10);
    if (!v) {
      // 清空开始日期：连同到期日一起清空，避免出现"只有到期日"的孤儿任务
      updateTaskLocal(t, { startDate: null, dueDate: null });
      return;
    }
    const patch = { startDate: v + startTime };
    if (!t.dueDate || !startDay || dueDay === startDay) {
      // 原本无日期或单日任务：整体平移到新日期，保持单日
      patch.dueDate = v + (t.dueDate ? dueTime : startTime);
    } else if (dueDay < v) {
      // 范围任务：开始日期晚于到期日期 → 到期日跟随，避免倒挂
      patch.dueDate = v + dueTime;
    }
    // 其余情况（合法范围调整开始日期）：到期日保持不变
    updateTaskLocal(t, patch);
  },
});
// 结束日期（独立于开始日期，支持时间范围）
const endDateStr = computed({
  get: () => props.task.dueDate?.slice(0, 10) || '',
  set: (v) => {
    const t = props.task;
    const time = t.isAllDay ? 'T00:00:00' : 'T' + (t.dueDate?.slice(11) || '09:00:00');
    const start = t.startDate?.slice(0, 10);
    if (!start) {
      // 无开始日期：直接设为该日的单日任务（清空则一并清除）
      if (v) updateTaskLocal(t, { startDate: v + time, dueDate: v + time });
      else updateTaskLocal(t, { startDate: null, dueDate: null });
      return;
    }
    updateTaskLocal(t, { dueDate: v && v >= start ? v + time : start + time });
  },
});
const timeStr = computed({
  get: () => props.task.startDate?.slice(11, 16) || '09:00',
  set: (v) => {
    if (!props.task.startDate) return;
    const date = props.task.startDate.slice(0, 10);
    const endDate = (props.task.dueDate || props.task.startDate).slice(0, 10);
    updateTaskLocal(props.task, {
      startDate: date + 'T' + v + ':00',
      dueDate: endDate + 'T' + v + ':00',
    });
  },
});

function setPriority(v) {
  updateTaskLocal(props.task, { priority: v });
  openMenu.value = '';
}
function setProject(id) {
  updateTaskLocal(props.task, { projectId: id });
  openMenu.value = '';
}
function toggleAllDay() {
  updateTaskLocal(props.task, { isAllDay: !props.task.isAllDay });
}
function setRepeat(v) {
  updateTaskLocal(props.task, { repeatFlag: v });
  openMenu.value = '';
}

const repeatOptions = [
  { value: '', label: '不重复' },
  { value: 'RRULE:FREQ=DAILY', label: '每天' },
  { value: 'RRULE:FREQ=WEEKLY', label: '每周' },
  { value: 'RRULE:FREQ=MONTHLY', label: '每月' },
  { value: 'RRULE:FREQ=YEARLY', label: '每年' },
];

// 子任务
const newSub = ref('');
const subs = computed(() => subtasksOf(props.task.id));
async function addSub() {
  if (!newSub.value.trim()) return;
  await addTask({
    title: newSub.value.trim(),
    parentId: props.task.id,
    projectId: props.task.projectId,
    startDate: props.task.startDate,
    dueDate: props.task.dueDate,
    isAllDay: props.task.isAllDay,
  });
  newSub.value = '';
}

// 标签：可选择已有标签，输入新标签回车自动新增
const tagInput = ref('');
const tagMenuOpen = ref(false);
const tagSuggestions = computed(() => {
  const q = tagInput.value.trim().toLowerCase();
  return allTags.value.filter(
    (t) => !props.task.tags.includes(t) && (!q || t.toLowerCase().includes(q))
  );
});
function addTag(value) {
  const v = (value ?? tagInput.value).trim().replace(/,/g, '');
  if (v && !props.task.tags.includes(v)) {
    updateTaskLocal(props.task, { tags: [...props.task.tags, v] });
  }
  tagInput.value = '';
  tagMenuOpen.value = false;
}
function pickTag(tag) {
  addTag(tag);
}
const tagInputEl = ref(null);
const tagSuggestEl = ref(null);
async function onTagFocus() {
  tagMenuOpen.value = true;
  await nextTick();
  placeDropdown(tagSuggestEl.value, tagInputEl.value);
}
function removeTag(tag) {
  updateTaskLocal(props.task, { tags: props.task.tags.filter((t) => t !== tag) });
}
function onTagBlur() {
  // 延迟关闭，让下拉项的 mousedown 先执行
  setTimeout(() => (tagMenuOpen.value = false), 150);
}

// ---------- 备注 Markdown：通用组件 MarkdownEditor ----------
function onContentUpdate(v) {
  updateTaskLocal(props.task, { content: v });
}

function close() {
  closeTaskDetail();
}
async function remove() {
  if (confirm('确定删除该任务吗？（含子任务）')) {
    await deleteTaskLocal(props.task);
  }
}

const doneSubs = computed(() => subs.value.filter((s) => s.status === 2).length);

const createdLabel = computed(() => {
  if (!props.task.createdAt) return '';
  return `创建于 ${props.task.createdAt.slice(0, 16).replace('T', ' ')}`;
});
const completedLabel = computed(() => {
  if (props.task.status !== 2 || !props.task.completedAt) return '';
  return `完成于 ${props.task.completedAt.slice(0, 16).replace('T', ' ')}`;
});

// ---------- 就地弹层定位 ----------
const PANEL_W = 380;
const PANEL_MAX_H = Math.min(560, Math.round(window.innerHeight * 0.72));
const panelEl = ref(null);
// 拖动 / 缩放后的自定义位置与尺寸（null = 未自定义，按锚点定位）
const custom = ref(null);
const panelStyle = computed(() => {
  const a = store.detailAnchor;
  // 坐标非法时兜底：视口居中偏上
  const x = a && Number.isFinite(a.x) ? a.x : Math.round(window.innerWidth / 2);
  const y = a && Number.isFinite(a.y) ? a.y : 80;
  let left = x + 10;
  let top = y - 16;
  if (left + PANEL_W > window.innerWidth - 12) left = Math.max(12, x - PANEL_W - 10);
  if (top + PANEL_MAX_H > window.innerHeight - 12) top = Math.max(12, y - PANEL_MAX_H - 10);
  const style = { left: left + 'px', top: top + 'px', width: PANEL_W + 'px', maxHeight: PANEL_MAX_H + 'px' };
  if (custom.value) {
    style.left = custom.value.left + 'px';
    style.top = custom.value.top + 'px';
    if (custom.value.width != null) style.width = custom.value.width + 'px';
    if (custom.value.height != null) {
      style.height = custom.value.height + 'px';
      style.maxHeight = custom.value.height + 'px';
    }
  }
  return style;
});

// ---------- 弹窗拖动（标题行） / 边缘缩放 ----------
const MIN_W = 320;
const MIN_H = 220;
const EDGE = 8; // 距视口边缘最小留白
let drag = null;

function beginDrag(mode, e) {
  if (e.button !== 0) return;
  const r = panelEl.value.getBoundingClientRect();
  if (!custom.value) custom.value = { left: r.left, top: r.top };
  tagMenuOpen.value = false; // fixed 定位的标签下拉不随面板移动，拖动时先收起
  drag = { mode, x: e.clientX, y: e.clientY, rect: r };
  document.body.style.userSelect = 'none';
  e.preventDefault();
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', endDrag);
}
function startMove(e) {
  if (e.target.closest('.td-close, .td-action')) return;
  beginDrag('move', e);
}
function onDragMove(e) {
  if (!drag) return;
  const { mode, x, y, rect } = drag;
  const dx = e.clientX - x;
  const dy = e.clientY - y;
  if (mode === 'move') {
    const left = Math.min(Math.max(EDGE, rect.left + dx), window.innerWidth - EDGE - rect.width);
    const top = Math.min(Math.max(EDGE, rect.top + dy), window.innerHeight - EDGE - rect.height);
    custom.value = { ...custom.value, left, top };
    return;
  }
  let left = custom.value.left;
  let top = custom.value.top;
  let width = rect.width;
  let height = rect.height;
  if (mode.includes('e')) width = Math.max(MIN_W, Math.min(rect.width + dx, window.innerWidth - EDGE - rect.left));
  if (mode.includes('w')) {
    width = Math.max(MIN_W, Math.min(rect.width - dx, rect.right - EDGE));
    left = rect.right - width;
  }
  if (mode.includes('s')) height = Math.max(MIN_H, Math.min(rect.height + dy, window.innerHeight - EDGE - rect.top));
  if (mode.includes('n')) {
    height = Math.max(MIN_H, Math.min(rect.height - dy, rect.bottom - EDGE));
    top = rect.bottom - height;
  }
  const patch = { left, top, width };
  // 只有上下边缘参与缩放时才固定高度；否则保持内容自适应
  if (mode.includes('n') || mode.includes('s')) patch.height = height;
  custom.value = { ...custom.value, ...patch };
}
function endDrag() {
  drag = null;
  document.body.style.userSelect = '';
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', endDrag);
}
onBeforeUnmount(endDrag);
</script>

<template>
  <div class="td-backdrop" @mousedown.self="close" @contextmenu.prevent>
    <div ref="panelEl" class="task-detail" :style="panelStyle" @mousedown.stop>
      <div class="td-header-row" @mousedown="startMove">
        <Icon name="panel-close" :size="16" class="td-close" @click="close" />
        <div class="td-actions">
          <span class="td-action" title="删除任务" @click="remove"><Icon name="delete" :size="15" /></span>
        </div>
      </div>

      <div class="td-body">
        <!-- 标题 + 完成勾选 -->
        <div class="td-title-row">
          <span
            class="td-check"
            :style="{ color: task.status === 2 ? 'var(--grey-20)' : activePriority.color }"
            @click="toggleTask(task)"
          >
            <Icon v-if="task.status === 2" name="calendar-complete" :size="20" />
            <Icon v-else name="calendar-checkbox" :size="20" />
          </span>
          <input v-model="title" class="td-title-input" placeholder="标题" />
        </div>

        <!-- 属性行 -->
        <div class="td-props">
          <div class="td-prop">
            <Icon name="date-unselected" :size="15" class="td-prop-icon" />
            <div class="td-prop-main">
              <div class="td-prop-row">
                <DatePicker ref="startPickRef" v-model="dateStr" title="开始日期" @click.stop />
                <span v-if="endDateStr && endDateStr !== dateStr" class="range-sep">→</span>
                <DatePicker
                  v-if="endDateStr && endDateStr !== dateStr"
                  ref="endPickRef"
                  v-model="endDateStr"
                  title="结束日期"
                  @click.stop
                />
              </div>
              <div class="td-prop-row" style="margin-top: 3px">
                <input v-if="!task.isAllDay" v-model="timeStr" type="time" class="inline-input small" @click.stop />
              </div>
              <label class="all-day-row" @click.stop>
                <input type="checkbox" :checked="task.isAllDay" @change="toggleAllDay" />
                全天
              </label>
            </div>
          </div>

          <div class="td-prop" @click="openMenu = openMenu === 'repeat' ? '' : 'repeat'">
            <Icon name="repeat" :size="15" class="td-prop-icon" />
            <span class="td-prop-text">
              {{ repeatOptions.find((r) => r.value === task.repeatFlag)?.label || '不重复' }}
            </span>
            <div v-if="openMenu === 'repeat'" class="preset-popover" @click.stop>
              <div v-for="r in repeatOptions" :key="r.value" class="menu-row" :class="{ sel: r.value === task.repeatFlag }" @click="setRepeat(r.value)">
                <span>{{ r.label }}</span>
              </div>
            </div>
          </div>

          <div class="td-prop" @click="openMenu = openMenu === 'priority' ? '' : 'priority'">
            <Icon :name="activePriority.icon" :size="15" class="td-prop-icon" :style="{ color: activePriority.color }" />
            <span class="td-prop-text">{{ activePriority.label }}</span>
            <div v-if="openMenu === 'priority'" class="preset-popover" @click.stop>
              <div v-for="p in priorities" :key="p.value" class="menu-row" :class="{ sel: p.value === task.priority }" @click="setPriority(p.value)">
                <Icon :name="p.icon" :size="15" :style="{ color: p.color }" />
                <span>{{ p.label }}</span>
              </div>
            </div>
          </div>

          <div class="td-prop" @click="openMenu = openMenu === 'list' ? '' : 'list'">
            <Icon name="move-list" :size="15" class="td-prop-icon" />
            <span class="td-prop-text">{{ project?.emoji }} {{ project?.name }}</span>
            <div v-if="openMenu === 'list'" class="preset-popover" @click.stop>
              <div v-for="p in store.projects" :key="p.id" class="menu-row" :class="{ sel: p.id === task.projectId }" @click="setProject(p.id)">
                <span v-if="p.emoji" class="emoji">{{ p.emoji }}</span>
                <Icon v-else name="inbox-list" :size="14" />
                <span>{{ p.name }}</span>
              </div>
            </div>
          </div>

          <!-- 标签 -->
          <div class="td-prop tags-prop">
            <Icon name="tag" :size="15" class="td-prop-icon" />
            <div class="tags-wrap">
              <span v-for="tag in task.tags" :key="tag" class="tag-chip" @click="removeTag(tag)">
                {{ tag }} <Icon name="close" :size="9" />
              </span>
              <input
                ref="tagInputEl"
                v-model="tagInput"
                class="tag-inline-input"
                placeholder="添加标签"
                @keydown.enter.prevent="addTag()"
                @focus="onTagFocus"
                @input="tagMenuOpen = true"
                @blur="onTagBlur"
                @click.stop
              />
              <div v-if="tagMenuOpen" ref="tagSuggestEl" class="tag-suggest" @mousedown.prevent>
                <div
                  v-for="tag in tagSuggestions"
                  :key="tag"
                  class="tag-suggest-item"
                  @click="pickTag(tag)"
                >
                  <Icon name="tag" :size="12" />
                  <span>{{ tag }}</span>
                </div>
                <div v-if="tagInput.trim() && !tagSuggestions.includes(tagInput.trim())" class="tag-suggest-new" @click="addTag()">
                  <Icon name="add-small" :size="12" />
                  <span>新建标签 “{{ tagInput.trim() }}”</span>
                </div>
                <div v-if="!tagSuggestions.length && !tagInput.trim()" class="tag-suggest-empty">暂无其他标签</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 备注（Markdown 编辑器：左右分栏实时预览 + 右键格式化） -->
        <MarkdownEditor
          :model-value="task.content"
          placeholder="备注…（支持 Markdown，选中文本右键可快捷格式化）"
          @update:model-value="onContentUpdate"
        />

        <!-- 子任务 -->
        <div class="td-subtasks">
          <div class="td-sub-title" v-if="subs.length">子任务 {{ doneSubs }}/{{ subs.length }}</div>
          <div v-for="s in subs" :key="s.id" class="td-sub-row">
            <span class="td-check small" :style="{ color: s.status === 2 ? 'var(--grey-20)' : 'var(--grey-60)' }" @click="toggleTask(s)">
              <Icon :name="s.status === 2 ? 'calendar-complete' : 'calendar-checkbox'" :size="16" />
            </span>
            <input
              class="td-sub-input"
              :class="{ done: s.status === 2 }"
              :value="s.title"
              @change="updateTaskLocal(s, { title: $event.target.value })"
            />
            <span class="td-sub-del" @click="deleteTaskLocal(s)"><Icon name="close" :size="11" /></span>
          </div>
          <div class="td-sub-add">
            <Icon name="add-small" :size="13" />
            <input v-model="newSub" placeholder="添加子任务" @keydown.enter="addSub" />
          </div>
        </div>

        <div class="td-meta">
          <span v-if="createdLabel">{{ createdLabel }}</span>
          <span v-if="completedLabel">{{ completedLabel }}</span>
        </div>
      </div>

      <!-- 边缘缩放手柄（置于面板内侧，避免被 overflow: hidden 裁剪） -->
      <span
        v-for="d in ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']"
        :key="d"
        class="td-rz"
        :class="'td-rz-' + d"
        @mousedown="beginDrag(d, $event)"
      ></span>
    </div>

  </div>
</template>

<style scoped>
.td-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: transparent;
}
.task-detail {
  position: fixed;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow-float);
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-float);
  animation: pop-in 0.24s var(--ease-spring);
  overflow: hidden;
  user-select: text;
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); filter: blur(6px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.td-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px 2px;
  flex: none;
  cursor: move;
}
/* 边缘缩放手柄 */
.td-rz {
  position: absolute;
  z-index: 20;
}
.td-rz-n { top: 0; left: 10px; right: 10px; height: 5px; cursor: ns-resize; }
.td-rz-s { bottom: 0; left: 10px; right: 10px; height: 5px; cursor: ns-resize; }
.td-rz-e { right: 0; top: 10px; bottom: 10px; width: 5px; cursor: ew-resize; }
.td-rz-w { left: 0; top: 10px; bottom: 10px; width: 5px; cursor: ew-resize; }
.td-rz-ne { top: 0; right: 0; width: 12px; height: 12px; cursor: nesw-resize; }
.td-rz-nw { top: 0; left: 0; width: 12px; height: 12px; cursor: nwse-resize; }
.td-rz-se { bottom: 0; right: 0; width: 12px; height: 12px; cursor: nwse-resize; }
.td-rz-sw { bottom: 0; left: 0; width: 12px; height: 12px; cursor: nesw-resize; }
.td-close {
  cursor: pointer;
  color: var(--grey-40);
  border-radius: 6px;
  padding: 3px;
  transition: all 0.2s var(--ease-spring);
}
.td-close:hover {
  background: var(--grey-5);
  color: var(--front-color);
}
.td-actions {
  display: flex;
  gap: 6px;
}
.td-action {
  cursor: pointer;
  color: var(--grey-40);
  padding: 3px;
  border-radius: 6px;
  transition: all 0.2s var(--ease-spring);
}
.td-action:hover {
  background: var(--grey-5);
  color: var(--warn-red);
}

.td-body {
  flex: 1;
  overflow-y: auto;
  padding: 2px 14px 14px;
}
.td-title-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
}
.td-check {
  cursor: pointer;
  display: inline-flex;
  margin-top: 3px;
  flex: none;
}
.td-check.small {
  margin-top: 0;
}
.td-title-input {
  flex: 1;
  border: none;
  border-radius: var(--radius-control);
  font-size: 17px;
  font-weight: 600;
  line-height: 24px;
  padding: 2px 6px;
  color: var(--front-color);
  min-width: 0;
  transition: background 0.2s var(--ease-spring);
}
.td-title-input:hover,
.td-title-input:focus {
  background: rgba(255, 255, 255, 0.55);
}

.td-props {
  margin: 8px 0;
  border-top: 1px solid var(--grey-5);
  border-bottom: 1px solid var(--grey-5);
  padding: 3px 0;
}
.td-prop {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s var(--ease-spring);
}
.td-prop:hover {
  background: var(--grey-5);
}
.td-prop-icon {
  color: var(--grey-60);
  flex: none;
}
.td-prop-text {
  font-size: 13px;
  color: var(--grey-80);
}
.td-prop-main {
  flex: 1;
  min-width: 0;
}
.td-prop-row {
  display: flex;
  gap: 8px;
}
.inline-input {
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  font-size: 13px;
  color: var(--grey-80);
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  width: 124px;
  padding: 2px 4px;
  transition: all 0.2s var(--ease-spring);
}
.inline-input:hover {
  background: rgba(255, 255, 255, 0.72);
}
.inline-input:focus {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.78);
}
.inline-input.small {
  width: 76px;
}
.range-sep {
  color: var(--grey-40);
  font-size: 12px;
  margin: 0 2px;
}
.all-day-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--grey-40);
  margin-top: 2px;
  cursor: pointer;
}
.preset-popover {
  position: absolute;
  top: 34px;
  left: 6px;
  z-index: 30;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--glass-shadow-float);
  padding: 5px 0;
  width: 165px;
  animation: td-pop-in 0.22s var(--ease-spring);
}
@keyframes td-pop-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.menu-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 31px;
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
  transition: background 0.15s var(--ease-spring);
}
.menu-row:hover {
  background: var(--grey-5);
}
.menu-row.sel {
  color: var(--primary-color);
}
.emoji {
  font-size: 14px;
}

.tags-wrap {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
  flex: 1;
}
.tag-suggest {
  position: fixed;
  z-index: 1400;
  min-width: 150px;
  max-height: 180px;
  overflow-y: auto;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--glass-shadow-float);
  padding: 5px 0;
  animation: td-pop-in 0.22s var(--ease-spring);
}
.tag-suggest-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 30px;
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
  transition: background 0.15s var(--ease-spring);
}
.tag-suggest-item:hover {
  background: var(--grey-5);
}
.tag-suggest-item .icon {
  color: var(--grey-60);
}
.tag-suggest-new {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 30px;
  font-size: 13px;
  color: var(--primary-color);
  cursor: pointer;
  border-top: 1px solid var(--grey-5);
  transition: background 0.15s var(--ease-spring);
}
.tag-suggest-new:hover {
  background: var(--grey-5);
}
.tag-suggest-empty {
  padding: 8px 14px;
  font-size: 12px;
  color: var(--grey-40);
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--grey-8);
  font-size: 12px;
  color: var(--grey-80);
  cursor: pointer;
  transition: background 0.2s var(--ease-spring);
}
.tag-chip:hover {
  background: var(--grey-13);
}
.tag-inline-input {
  border: none;
  font-size: 13px;
  min-width: 76px;
  flex: 1;
  background: transparent;
}

.td-subtasks {
  margin-top: 4px;
}
.td-sub-title {
  font-size: 12px;
  color: var(--grey-40);
  margin: 5px 0;
}
.td-sub-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 2px;
  border-radius: 8px;
  transition: background 0.2s var(--ease-spring);
}
.td-sub-row:hover {
  background: var(--grey-5);
}
.td-sub-input {
  flex: 1;
  border: none;
  font-size: 13px;
  color: var(--front-color);
  background: transparent;
  min-width: 0;
}
.td-sub-input.done {
  color: var(--grey-40);
  text-decoration: line-through;
}
.td-sub-del {
  visibility: hidden;
  color: var(--grey-40);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  transition: color 0.15s var(--ease-spring);
}
.td-sub-row:hover .td-sub-del {
  visibility: visible;
}
.td-sub-del:hover {
  color: var(--warn-red);
}
.td-sub-add {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 2px;
  color: var(--grey-60);
  border-radius: 8px;
  transition: background 0.2s var(--ease-spring);
}
.td-sub-add:hover {
  background: var(--grey-5);
}
.td-sub-add input {
  border: none;
  font-size: 13px;
  background: transparent;
  flex: 1;
}

.td-meta {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--grey-30);
}
</style>
