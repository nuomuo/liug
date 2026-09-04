<script setup>
import { computed, ref } from 'vue';
import { store, allTags, showToast } from '../store.js';
import { api } from '../api.js';
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

// 组级复选框：全选 / 清空该组清单（并取消标签筛选）
function toggleProjectGroup() {
  const ids = store.projects.map((p) => p.id);
  const allSelected = ids.length > 0 && ids.every((id) => store.selectedProjectIds.includes(id));
  store.selectedProjectIds = allSelected ? [] : ids;
  if (!allSelected) store.selectedTag = '';
}

function toggleTag(tag) {
  store.selectedTag = store.selectedTag === tag ? '' : tag;
}

function projectCount(p) {
  return store.tasks.filter((t) => t.projectId === p.id && t.status === 0).length;
}

// ---------- 添加清单（弹窗，复用编辑弹层样式） ----------
const addingList = ref(false);
const newListName = ref('');

function showAddList() {
  addingList.value = true;
  newListName.value = '';
  editForm.value = { name: '', emoji: '', color: colorPresets[Math.floor(Math.random() * colorPresets.length)] };
}

async function createList() {
  const name = newListName.value.trim();
  if (!name) {
    showToast('请输入清单名称');
    return;
  }
  try {
    const p = await api.createProject({
      name,
      emoji: editForm.value.emoji,
      color: editForm.value.color,
    });
    store.projects.push(p);
    showToast(`清单「${name}」已创建`);
    addingList.value = false;
  } catch (e) {
    showToast(e?.data?.error || '创建清单失败');
  }
}

// ---------- 编辑清单（右键：改名 / 图标 / 颜色 / 删除） ----------
const editing = ref(null); // 正在编辑的清单对象
const editForm = ref({ name: '', emoji: '', color: '#484553' });
const editPos = ref({ x: 0, y: 0 });

const emojiPresets = ['', '📋', '💼', '🏠', '🛒', '🎯', '📚', '✈️', '💡', '🎨', '💪', '💰', '🎮', '❤️', '⭐', '🔥'];
const colorPresets = [
  '#484553', '#0c9e6e', '#2f6fe4', '#d9544d',
  '#e8852c', '#8b6ff0', '#0caeae', '#e06a9f',
  '#7a5af8', '#c9a34c', '#5f8b4b', '#3f5f7a',
];

function openProjectMenu(p, e) {
  editing.value = p;
  editForm.value = { name: p.name, emoji: p.emoji || '', color: p.color || '#484553' };
  // 防止弹层超出视口
  editPos.value = {
    x: Math.min(e.clientX, window.innerWidth - 260),
    y: Math.min(e.clientY, window.innerHeight - 330),
  };
}
function closeProjectMenu() {
  editing.value = null;
}

async function saveProject() {
  const p = editing.value;
  if (!p) return;
  const name = editForm.value.name.trim();
  if (!name) {
    showToast('清单名称不能为空');
    return;
  }
  try {
    const updated = await api.updateProject(p.id, {
      name,
      emoji: editForm.value.emoji,
      color: editForm.value.color,
    });
    Object.assign(p, updated);
    showToast('清单已更新');
    closeProjectMenu();
  } catch (e) {
    showToast(e?.data?.error || '更新清单失败');
  }
}

async function removeProject() {
  const p = editing.value;
  if (!p) return;
  if (p.id === 1) {
    showToast('收集箱不可删除');
    return;
  }
  if (!confirm(`删除清单「${p.name}」及其所有任务？`)) return;
  try {
    await api.deleteProject(p.id);
    store.projects = store.projects.filter((x) => x.id !== p.id);
    store.tasks = store.tasks.filter((t) => t.projectId !== p.id);
    const i = store.selectedProjectIds.indexOf(p.id);
    if (i >= 0) store.selectedProjectIds.splice(i, 1);
    showToast('清单已删除');
    closeProjectMenu();
  } catch (e) {
    showToast(e?.data?.error || '删除清单失败');
  }
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
      <div class="group-header">
        <span class="group-label" @click="collapsed.list = !collapsed.list">
          <span class="collapse-arrow" :class="{ collapsed: collapsed.list }">
            <Icon name="down-arrow" :size="12" />
          </span>
          <span class="group-name">清单</span>
        </span>
        <span
          class="mini-checkbox"
          :class="{ checked: store.selectedProjectIds.length > 0 }"
          @click.stop="toggleProjectGroup"
        >
          <Icon name="right-panel-all-selected" :size="9" />
        </span>
      </div>
      <template v-if="!collapsed.list">
        <li
          v-for="p in store.projects"
          :key="p.id"
          class="option-item"
          :title="`${p.name}（右键编辑）`"
          @click="toggleProject(p.id)"
          @contextmenu.prevent="openProjectMenu(p, $event)"
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
        <li class="option-item muted" @click="showAddList">
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

    <!-- 清单编辑弹层：右键清单打开（传送到 body，避免被左侧玻璃面板的层叠上下文遮挡） -->
    <template v-if="editing">
      <Teleport to="body">
        <div class="proj-edit-backdrop" @mousedown.self="closeProjectMenu"></div>
        <div class="proj-edit" :style="{ left: editPos.x + 'px', top: editPos.y + 'px' }">
          <input
            v-model="editForm.name"
            class="proj-edit-name"
            maxlength="30"
            placeholder="清单名称"
            @keydown.enter="saveProject"
            @keydown.esc="closeProjectMenu"
          />
          <div class="proj-edit-label">图标</div>
          <div class="emoji-grid">
            <span
              v-for="em in emojiPresets"
              :key="em"
              class="emoji-cell"
              :class="{ sel: editForm.emoji === em }"
              @click="editForm.emoji = em"
            >{{ em || '◦' }}</span>
          </div>
          <div class="proj-edit-label">颜色（决定任务标签底色）</div>
          <div class="color-grid">
            <span
              v-for="c in colorPresets"
              :key="c"
              class="color-cell"
              :class="{ sel: editForm.color === c }"
              :style="{ background: c }"
              @click="editForm.color = c"
            ></span>
            <label class="color-cell custom" :style="{ background: editForm.color }" title="自定义颜色">
              <input type="color" v-model="editForm.color" />
            </label>
          </div>
          <div class="proj-edit-actions">
            <button v-if="editing.id !== 1" class="proj-del" @click="removeProject">删除</button>
            <span class="spacer"></span>
            <button class="proj-cancel" @click="closeProjectMenu">取消</button>
            <button class="proj-save" @click="saveProject">保存</button>
          </div>
        </div>
      </Teleport>
    </template>

    <!-- 新增清单弹窗 -->
    <template v-if="addingList">
      <Teleport to="body">
        <div class="proj-edit-backdrop" @mousedown.self="addingList = false"></div>
        <div class="proj-edit proj-edit-center">
          <div class="proj-edit-title">新增清单</div>
          <input
            v-model="newListName"
            class="proj-edit-name"
            maxlength="30"
            placeholder="清单名称"
            autofocus
            @keydown.enter="createList"
            @keydown.esc="addingList = false"
          />
          <div class="proj-edit-label">图标</div>
          <div class="emoji-grid">
            <span
              v-for="em in emojiPresets"
              :key="em"
              class="emoji-cell"
              :class="{ sel: editForm.emoji === em }"
              @click="editForm.emoji = em"
            >{{ em || '◦' }}</span>
          </div>
          <div class="proj-edit-label">颜色（决定任务标签底色）</div>
          <div class="color-grid">
            <span
              v-for="c in colorPresets"
              :key="c"
              class="color-cell"
              :class="{ sel: editForm.color === c }"
              :style="{ background: c }"
              @click="editForm.color = c"
            ></span>
            <label class="color-cell custom" :style="{ background: editForm.color }" title="自定义颜色">
              <input type="color" v-model="editForm.color" />
            </label>
          </div>
          <div class="proj-edit-actions">
            <span class="spacer"></span>
            <button class="proj-cancel" @click="addingList = false">取消</button>
            <button class="proj-save" @click="createList">创建</button>
          </div>
        </div>
      </Teleport>
    </template>
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
/* ---------- 清单编辑弹层 ---------- */
.proj-edit-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
}
.proj-edit {
  position: fixed;
  z-index: 1201;
  width: 244px;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  padding: 14px;
  animation: proj-edit-in 0.22s var(--ease-spring);
}
@keyframes proj-edit-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.proj-edit-center {
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
}
.proj-edit-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
}
.proj-edit-name {
  width: 100%;
  height: 34px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  padding: 0 10px;
  font-size: 13px;
  outline: none;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.6);
}
.proj-edit-name:focus {
  border-color: var(--primary-color);
}
.proj-edit-label {
  font-size: 11px;
  color: var(--grey-40);
  margin: 10px 0 6px;
}
.emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
}
.emoji-cell {
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--grey-30);
}
.emoji-cell:hover {
  background: var(--grey-5);
}
.emoji-cell.sel {
  background: var(--grey-10);
  outline: 1px solid var(--primary-color);
}
.color-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}
.color-cell {
  height: 22px;
  border-radius: 5px;
  cursor: pointer;
  position: relative;
}
.color-cell:hover {
  filter: brightness(1.12);
}
.color-cell.sel {
  outline: 2px solid var(--front-color);
  outline-offset: 1px;
}
.color-cell.custom {
  overflow: hidden;
}
.color-cell.custom input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.proj-edit-actions {
  display: flex;
  align-items: center;
  margin-top: 12px;
}
.proj-edit-actions .spacer {
  flex: 1;
}
.proj-edit-actions button {
  height: 30px;
  padding: 0 16px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s var(--ease-spring);
}
.proj-del {
  border-color: transparent;
  background: none;
  color: #d9544d;
  padding: 0 8px !important;
}
.proj-del:hover {
  background: rgba(217, 84, 77, 0.1);
}
.proj-cancel {
  background: rgba(255, 255, 255, 0.6);
  color: var(--grey-60);
  border-color: rgba(29, 29, 31, 0.12) !important;
}
.proj-cancel:hover {
  color: var(--front-color);
}
.proj-save {
  background: var(--primary-color);
  color: #fff;
}
.proj-save:hover {
  background: var(--primary-hover-color);
}
.empty-hint {
  font-size: 12px;
  color: var(--grey-30);
  padding: 4px 16px 4px 26px;
}
</style>
