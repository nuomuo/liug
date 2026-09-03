<script setup>
import { ref, computed, onMounted, nextTick } from 'vue';
import { store, addTask, showToast, getProject, fmtDate } from '../store.js';
import Icon from './Icon.vue';

const title = ref('');
const content = ref('');
const priority = ref(0);
const projectId = ref(null);
const tags = ref([]);
const allDay = ref(true);
const dateStr = ref('');
const endDateStr = ref('');
const timeStr = ref('09:00');

const inputEl = ref(null);
onMounted(() => {
  const preset = store.quickAdd.presetDate;
  if (preset) {
    dateStr.value = fmtDate(preset);
    // 带具体时分（周视图双击）→ 定时任务；否则默认全天
    if (preset.getHours() || preset.getMinutes()) {
      allDay.value = false;
      const p = (n) => String(n).padStart(2, '0');
      timeStr.value = `${p(preset.getHours())}:${p(preset.getMinutes())}`;
    }
  }
  // 从四象限添加：预置与象限对应的优先级（q1→高5、q2→中3、q3→低1、q4→无0）
  const q = store.quickAdd.presetQuadrant;
  if (q) {
    priority.value = q.priority ?? 0;
  }
  projectId.value = store.projects[0]?.id ?? null;
  nextTick(() => inputEl.value?.focus());
});

const activeProject = computed(() => getProject(projectId.value) || store.projects[0]);

const priorities = [
  { value: 0, label: '无', icon: 'priority-0', color: 'var(--grey-60)' },
  { value: 1, label: '低', icon: 'priority-1', color: '#4772fa' },
  { value: 3, label: '中', icon: 'priority-2', color: '#faa80c' },
  { value: 5, label: '高', icon: 'priority-3', color: '#e13e39' },
];
const activePriority = computed(() => priorities.find((p) => p.value === priority.value) || priorities[0]);

const allTags = computed(() => {
  const s = new Set();
  for (const t of store.tasks) for (const tag of t.tags) s.add(tag);
  return [...s];
});

// 预设浮层
const openMenu = ref('');

const datePreview = computed(() => {
  if (!dateStr.value) return '';
  const d = new Date(dateStr.value + 'T00:00:00');
  const today = new Date();
  const fmt = `${d.getMonth() + 1}月${d.getDate()}日`;
  const base =
    fmtDate(d) === fmtDate(today)
      ? '今天'
      : fmtDate(d) === fmtDate(new Date(today.getTime() + 86400000))
        ? '明天'
        : fmt;
  if (endDateStr.value && endDateStr.value !== dateStr.value) {
    const e = new Date(endDateStr.value + 'T00:00:00');
    return `${base} - ${e.getMonth() + 1}月${e.getDate()}日`;
  }
  return base;
});

function quickDate(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  dateStr.value = fmtDate(d);
  openMenu.value = '';
}

// 结束日期跟随开始日期（自动下限钳制）
function onEndDateInput() {
  if (endDateStr.value && endDateStr.value < dateStr.value) dateStr.value = endDateStr.value;
}
function onStartDateInput() {
  if (endDateStr.value && dateStr.value > endDateStr.value) endDateStr.value = dateStr.value;
}

async function submit() {
  if (!title.value.trim()) {
    showToast('请输入任务标题');
    inputEl.value?.focus();
    return;
  }
  let startDate = null;
  let dueDate = null;
  if (dateStr.value) {
    const t = allDay.value
      ? 'T00:00:00'
      : `T${timeStr.value.length === 5 ? timeStr.value + ':00' : timeStr.value}`;
    startDate = dateStr.value + t;
    const end = endDateStr.value && endDateStr.value >= dateStr.value ? endDateStr.value : dateStr.value;
    dueDate = end + t;
  }
  await addTask({
    title: title.value.trim(),
    content: content.value,
    projectId: projectId.value,
    priority: priority.value,
    tags: tags.value,
    isAllDay: allDay.value,
    startDate,
    dueDate,
  });
  store.quickAdd = { open: false, presetDate: null, presetTask: null };
}

function toggleTag(tag) {
  const i = tags.value.indexOf(tag);
  if (i >= 0) tags.value.splice(i, 1);
  else tags.value.push(tag);
}
</script>

<template>
  <div class="popup-cover global-quick-add-wrapper" @mousedown.self="store.quickAdd = { open: false, presetDate: null, presetTask: null }">
    <div class="global-quick-add">
      <div class="tl-quick">
        <div class="task-input">
          <div class="task-title" @click="inputEl?.focus()">
            <input
              ref="inputEl"
              v-model="title"
              class="title-editor"
              type="text"
              placeholder="准备做什么？"
              @keydown.enter="submit"
            />
          </div>
          <textarea
            v-if="content || openMenu === 'more'"
            v-model="content"
            class="content-editor"
            placeholder="描述或其他信息…"
            rows="2"
          ></textarea>
        </div>

        <div class="global-footer">
          <div class="preset-wrapper">
            <!-- 日期 -->
            <div class="preset-item" :class="{ open: openMenu === 'date' }" @click="openMenu = openMenu === 'date' ? '' : 'date'">
              <Icon name="date-unselected" :size="16" />
              <span v-if="datePreview" class="preset-text">{{ datePreview }}{{ !allDay ? ' ' + timeStr : '' }}</span>
              <div v-if="openMenu === 'date'" class="preset-popover" @click.stop>
                <div class="quick-row">
                  <button @click="quickDate(0)">今天</button>
                  <button @click="quickDate(1)">明天</button>
                  <button @click="quickDate(7)">下周</button>
                </div>
                <div class="form-row labels-row">
                  <span>开始</span>
                  <span>结束</span>
                </div>
                <div class="form-row">
                  <input v-model="dateStr" type="date" @input="onStartDateInput" />
                  <input v-model="endDateStr" type="date" @input="onEndDateInput" />
                </div>
                <div class="form-row" style="margin-top: 6px">
                  <input v-model="timeStr" type="time" :disabled="allDay" />
                </div>
                <label class="check-row">
                  <input v-model="allDay" type="checkbox" />
                  全天
                </label>
              </div>
            </div>

            <!-- 优先级 -->
            <div class="preset-item" :class="{ open: openMenu === 'priority' }" @click="openMenu = openMenu === 'priority' ? '' : 'priority'">
              <Icon :name="activePriority.icon" :size="16" :style="{ color: activePriority.color }" />
              <div v-if="openMenu === 'priority'" class="preset-popover wide" @click.stop>
                <div
                  v-for="p in priorities"
                  :key="p.value"
                  class="menu-row"
                  :class="{ sel: p.value === priority }"
                  @click="priority = p.value; openMenu = ''"
                >
                  <Icon :name="p.icon" :size="16" :style="{ color: p.color }" />
                  <span>{{ p.label }}</span>
                </div>
              </div>
            </div>

            <!-- 清单 -->
            <div class="preset-item" :class="{ open: openMenu === 'list' }" @click="openMenu = openMenu === 'list' ? '' : 'list'">
              <Icon name="move-list" :size="16" />
              <span class="preset-text">{{ activeProject?.emoji || '' }} {{ activeProject?.name }}</span>
              <div v-if="openMenu === 'list'" class="preset-popover wide" @click.stop>
                <div
                  v-for="p in store.projects"
                  :key="p.id"
                  class="menu-row"
                  :class="{ sel: p.id === projectId }"
                  @click="projectId = p.id; openMenu = ''"
                >
                  <span v-if="p.emoji" class="emoji">{{ p.emoji }}</span>
                  <Icon v-else name="inbox-list" :size="14" />
                  <span>{{ p.name }}</span>
                </div>
              </div>
            </div>

            <!-- 标签 -->
            <div class="preset-item" :class="{ open: openMenu === 'tag' }" @click="openMenu = openMenu === 'tag' ? '' : 'tag'">
              <Icon name="tag" :size="16" />
              <span v-if="tags.length" class="preset-text">{{ tags.join(',') }}</span>
              <div v-if="openMenu === 'tag'" class="preset-popover wide" @click.stop>
                <div v-if="allTags.length" class="tag-cloud">
                  <span
                    v-for="tag in allTags"
                    :key="tag"
                    class="tag-chip"
                    :class="{ sel: tags.includes(tag) }"
                    @click="toggleTag(tag)"
                  >
                    {{ tag }}
                  </span>
                </div>
                <div v-else class="tag-empty">暂无历史标签</div>
                <input
                  class="tag-input"
                  placeholder="输入新标签后回车"
                  @keydown.enter.prevent="
                    ($event) => {
                      const v = $event.target.value.trim();
                      if (v && !tags.includes(v)) tags.push(v);
                      $event.target.value = '';
                    }
                  "
                />
              </div>
            </div>

            <!-- 更多：展开备注 -->
            <div class="preset-item" :class="{ open: openMenu === 'more' }" @click="openMenu = openMenu === 'more' ? '' : 'more'">
              <Icon name="more-titlebar" :size="16" />
            </div>
          </div>

          <button class="add-btn-submit" :disabled="!title.trim()" @click="submit">添加</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.global-quick-add-wrapper {
  display: flex;
  justify-content: center;
  text-align: center;
  z-index: 1040;
}
.global-quick-add {
  position: relative;
  top: 30vh;
  display: inline-flex;
  flex-direction: column;
  align-self: flex-start;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  width: 560px;
  max-width: 92vw;
  text-align: left;
  user-select: text;
  animation: qa-pop-in 0.28s var(--ease-spring);
}
@keyframes qa-pop-in {
  from { opacity: 0; transform: translateY(-10px) scale(0.97); filter: blur(6px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.tl-quick {
  position: relative;
}
.task-input {
  padding: 4px 14px;
  max-height: 40vh;
  overflow-y: auto;
}
.title-editor {
  width: 100%;
  border: none;
  font-size: 19px;
  font-weight: 500;
  line-height: 26px;
  padding: 10px 0 4px;
  color: var(--front-color);
  background: transparent;
}
.title-editor::placeholder {
  color: var(--grey-20);
  font-weight: 400;
}
.content-editor {
  width: 100%;
  border: none;
  font-size: 14px;
  line-height: 20px;
  color: var(--grey-80);
  resize: none;
  background: transparent;
}
.content-editor::placeholder {
  color: var(--grey-30);
}

.global-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 8px 12px;
  border-top: 1px solid var(--grey-5);
}
.preset-wrapper {
  display: flex;
  align-items: center;
  overflow: visible;
  flex: 1;
  min-width: 0;
}
.preset-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--grey-60);
  flex: none;
  transition: all 0.2s var(--ease-spring);
}
.preset-item:hover,
.preset-item.open {
  background: var(--grey-5);
  color: var(--front-color);
}
.preset-text {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
}

.preset-popover {
  position: absolute;
  top: 32px;
  left: 0;
  z-index: 20;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--glass-shadow-float);
  padding: 10px;
  width: 250px;
  text-align: left;
  animation: qa-menu-in 0.22s var(--ease-spring);
}
@keyframes qa-menu-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.preset-popover.wide {
  width: 150px;
  padding: 5px 0;
}
.quick-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.quick-row button {
  flex: 1;
  height: 28px;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: 999px;
  font-size: 12px;
  color: var(--grey-80);
  background: rgba(255, 255, 255, 0.5);
  transition: all 0.2s var(--ease-spring);
}
.quick-row button:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.78);
}
.labels-row {
  gap: 6px;
  font-size: 11px;
  color: var(--grey-40);
  margin-bottom: 4px;
}
.labels-row span {
  flex: 1;
}
.form-row {
  display: flex;
  gap: 6px;
}
.form-row input {
  flex: 1;
  min-width: 0;
  height: 28px;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: var(--radius-control);
  padding: 0 8px;
  font-size: 12px;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.5);
  transition: all 0.2s var(--ease-spring);
}
.form-row input:hover {
  background: rgba(255, 255, 255, 0.72);
}
.form-row input:focus {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.78);
}
.form-row input:disabled {
  background: var(--grey-3);
  color: var(--grey-30);
}
.check-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--grey-80);
  margin-top: 8px;
  cursor: pointer;
}
.menu-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 32px;
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
  font-size: 15px;
  /* 与无 emoji 行的 14px 图标对齐在同一竖向位置 */
  width: 15px;
  text-align: center;
  flex: none;
}
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 10px 8px;
  max-width: 240px;
}
.tag-chip {
  padding: 2px 11px;
  border-radius: 999px;
  background: var(--grey-5);
  font-size: 12px;
  color: var(--grey-80);
  cursor: pointer;
  transition: all 0.2s var(--ease-spring);
}
.tag-chip:hover {
  background: var(--grey-10);
}
.tag-chip.sel {
  background: var(--primary-color);
  color: #fff;
}
.tag-empty {
  font-size: 12px;
  color: var(--grey-40);
  padding: 6px 12px;
}
.tag-input {
  width: calc(100% - 20px);
  margin: 0 10px 10px;
  height: 28px;
  border: 1px solid rgba(29, 29, 31, 0.1);
  border-radius: var(--radius-control);
  padding: 0 8px;
  font-size: 12px;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.5);
  transition: all 0.2s var(--ease-spring);
}
.tag-input:focus {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.78);
}

.add-btn-submit {
  flex: none;
  margin-left: 8px;
  height: 30px;
  padding: 0 20px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--primary-hover-color), var(--primary-color));
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(74, 108, 247, 0.35);
  transition: all 0.2s var(--ease-spring);
}
.add-btn-submit:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 6px 18px rgba(74, 108, 247, 0.45);
}
.add-btn-submit:disabled {
  background: var(--grey-10);
  color: var(--grey-30);
  cursor: not-allowed;
  box-shadow: none;
}
</style>
