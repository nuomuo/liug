<script setup>
// 桌面四象限小组件页面（/quadrant）：由 pywebview 无边框透明置顶窗口加载
// 复用主应用四象限口径：q1→高(5)、q2→中(3)、q3→低(1)、q4→无(0)，拖拽换象限 = 改优先级
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import {
  store, checkAuth, loadBootstrap, updateTaskLocal, getProject, openTaskDetail, toggleTask, fmtDate, parseLocal,
} from '../store.js';
import Icon from './Icon.vue';
import TaskDetail from './TaskDetail.vue';
import QuickAdd from './QuickAdd.vue';

// 组件可能常驻桌面过夜，today 必须在每次计算时取新值（不能 setup 时算一次）
const today = () => fmtDate(new Date());

const QUADRANTS = [
  { key: 'q1', title: '重要且紧急', color: '#FF5F68', priority: 5 },
  { key: 'q2', title: '重要不紧急', color: '#FFB000', priority: 3 },
  { key: 'q3', title: '不重要但紧急', color: '#4772FA', priority: 1 },
  { key: 'q4', title: '不重要不紧急', color: '#0CCE9C', priority: 0 },
];

function quadrantOf(t) {
  if (t.priority === 5) return 'q1';
  if (t.priority === 3) return 'q2';
  if (t.priority === 1) return 'q3';
  return 'q4';
}

// 象限内分组：今天 / 最近7天 / 更远 / 无日期（与主应用 MatrixPage 一致）
function sectionOf(t) {
  if (!t.dueDate) return '无日期';
  const d = t.dueDate.slice(0, 10);
  if (d <= today()) return '今天';
  const diff = (new Date(d + 'T00:00:00') - new Date(today() + 'T00:00:00')) / 86400000;
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
  if (d === today()) return '今天';
  const diff = (new Date(d + 'T00:00:00') - new Date(today() + 'T00:00:00')) / 86400000;
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
  return t.dueDate.slice(0, 10) < today();
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
  await updateTaskLocal(t, { priority: q.priority });
}

function openDetail(e, t) {
  openTaskDetail(t, e.clientX, e.clientY);
}

function onDblClick(q) {
  store.quickAdd = { open: true, presetDate: new Date(), presetTask: null, presetQuadrant: q };
}

const total = computed(() => store.tasks.filter((t) => t.status === 0).length);

const detailTask = computed(() => {
  if (store.detailTaskId == null) return null;
  return (
    store.tasks.find((t) => t.id === store.detailTaskId) ||
    store.subtasks.find((t) => t.id === store.detailTaskId) ||
    null
  );
});

// ---------- 数据刷新：30s 轮询（页面隐藏时跳过）+ 窗口聚焦时立即刷新 ----------
const refreshing = ref(false);
async function refresh() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    if (store.user) {
      await loadBootstrap();
    } else {
      // 未登录：定期探测登录状态（用户可能在主界面窗口完成登录，cookie 两窗口共享）
      await checkAuth();
    }
  } catch {
    // 静默失败：主界面登出后本窗口仍持有旧 user，首次拉取会 401（已由 onUnauthorized 切回登录态）
  } finally {
    refreshing.value = false;
  }
}
function onFocus() {
  refresh();
  // 切出/切回前台后 WebView2 透明合成可能掉线（面板后露出窗口兜底底色），请后端重建一次
  window.pywebview?.api?.reassert_transparency?.();
}
let timer = null;

// ---------- 跨窗口实时同步：主界面登录/增删改任务后 storage 打点，此处立即刷新 ----------
function onStorage(e) {
  if (e.key === 'liug-sync') refresh();
}

// ---------- pywebview 窗口控制（浏览器里访问 /quadrant 时隐藏窗口按钮） ----------
const inPywebview = ref(false);
// 置顶状态：默认不置顶（不挡其他应用），图钉按钮切换，后端持久化到 data/widget.json
const pinned = ref(false);
async function onPywebviewReady() {
  inPywebview.value = true;
  try {
    const st = await window.pywebview?.api?.get_state?.();
    if (st) pinned.value = !!st.pin;
  } catch {
    /* get_state 不可用时保持默认 */
  }
}
async function togglePin() {
  try {
    const v = await window.pywebview?.api?.toggle_pin?.();
    if (typeof v === 'boolean') pinned.value = v;
  } catch {
    /* 忽略 */
  }
}
function closeWindow() {
  window.pywebview?.api?.close();
}
function minimizeWindow() {
  window.pywebview?.api?.minimize();
}
// 未登录提示卡：点击打开主界面窗口登录（浏览器访问 /quadrant 时跳回主应用首页）
function openMainWindow() {
  if (window.pywebview?.api?.open_main) window.pywebview.api.open_main();
  else window.location.href = '/';
}
// 缩放小组件窗口（等比步进 64x52，desktop_app 内夹在 420x320 ~ 1100x900，尺寸由后端持久化）
function zoom(dir) {
  window.pywebview?.api?.resize(64 * dir, 52 * dir);
}
function onWheel(e) {
  if (!e.ctrlKey) return;
  e.preventDefault(); // 阻止浏览器 Ctrl+滚轮页面缩放
  zoom(e.deltaY < 0 ? 1 : -1);
}

// ---------- 拖动窗口（标题栏专属） ----------
// 不用 pywebview 的 easy_drag（其监听任意 mousedown，拖任务/点缩放手柄都会带着窗口跑，
// 且 HTML5 拖拽吞掉 mouseup 后鼠标一动窗口就跟着飘）；也放弃了 WM_NCLBUTTONDOWN/HTCAPTION
// 系统原生拖动（实测在 WebView2 下窗口收到消息但不进入移动循环）。
// 最终采用与窗口缩放同款的指针方案（server/widget_window.py MoveSession）：
// 前端只发信号：begin_move() → pointermove 节流调 update_move() → end_move()，
// 光标坐标一律由后端 GetCursorPos 取（避开 Chromium DIP 与 Win32 物理像素的 DPI 差）。
function onHeaderPointerDown(e) {
  if (e.button !== 0) return;
  if (e.target.closest('.qw-actions')) return; // 右上角按钮区不触发拖动
  e.preventDefault();
  window.pywebview?.api?.begin_move?.();
  const el = e.currentTarget;
  el.setPointerCapture(e.pointerId); // 拖出窗口外仍持续收到 move/up
  let last = 0;
  const onMove = () => {
    const now = performance.now();
    if (now - last < 16) return; // ~60fps 节流，防 RPC 积压
    last = now;
    window.pywebview?.api?.update_move?.();
  };
  const onUp = () => {
    el.removeEventListener('pointermove', onMove);
    el.removeEventListener('pointerup', onUp);
    el.removeEventListener('pointercancel', onUp);
    window.pywebview?.api?.end_move?.();
  };
  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
  el.addEventListener('pointercancel', onUp);
}

// ---------- 拖拽边缘/角落缩放窗口 ----------
// frameless 窗口原生不支持边缘 resize，后端用 Win32 补齐（server/widget_window.py）。
// 前端只发信号：begin_resize(edge) → pointermove 节流调 update_resize() → end_resize()，
// 光标坐标一律由后端 GetCursorPos 取（避开 Chromium DIP 与 Win32 物理像素的 DPI 差）。
const RESIZE_EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'];
const EDGE_CURSORS = {
  n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
  ne: 'nesw-resize', sw: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize',
};
function onResizeDown(e, edge) {
  if (e.button !== 0) return;
  e.preventDefault();
  window.pywebview?.api?.begin_resize?.(edge);
  const el = e.currentTarget;
  el.setPointerCapture(e.pointerId); // 拖出窗口外仍持续收到 move/up
  let last = 0;
  const onMove = () => {
    const now = performance.now();
    if (now - last < 16) return; // ~60fps 节流，防 RPC 积压
    last = now;
    window.pywebview?.api?.update_resize?.();
  };
  const onUp = () => {
    el.removeEventListener('pointermove', onMove);
    el.removeEventListener('pointerup', onUp);
    el.removeEventListener('pointercancel', onUp);
    window.pywebview?.api?.end_resize?.();
  };
  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
  el.addEventListener('pointercancel', onUp);
}

// ---------- 半透明配色三档：玻璃白 / 主题色轻染 / 暗色（localStorage 记忆） ----------
const TINT_KEY = 'quadrant-widget-tint';
const TINTS = [
  { key: 'none', label: '玻璃白' },
  { key: 'theme', label: '主题色' },
  { key: 'dark', label: '暗色' },
];
const tint = ref(TINTS.some((t) => t.key === localStorage.getItem(TINT_KEY)) ? localStorage.getItem(TINT_KEY) : 'none');
function tintLabel() {
  return TINTS.find((t) => t.key === tint.value)?.label || '';
}
function cycleTint() {
  const i = TINTS.findIndex((t) => t.key === tint.value);
  tint.value = TINTS[(i + 1) % TINTS.length].key;
  localStorage.setItem(TINT_KEY, tint.value);
}

onMounted(() => {
  timer = setInterval(() => {
    if (!document.hidden) refresh();
  }, 30000);
  window.addEventListener('focus', onFocus);
  window.addEventListener('storage', onStorage);
  window.addEventListener('pywebviewready', onPywebviewReady);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  window.removeEventListener('focus', onFocus);
  window.removeEventListener('storage', onStorage);
  window.removeEventListener('pywebviewready', onPywebviewReady);
});
</script>

<template>
  <div class="qw-root" :class="'tint-' + tint" @wheel="onWheel">
    <div class="qw-panel">
      <div class="qw-header" @pointerdown="onHeaderPointerDown">
        <Icon name="matrix-sidebar" :size="16" />
        <span class="qw-title">四象限</span>
        <span class="qw-count" v-if="store.user && total">{{ total }}</span>
        <div class="qw-actions">
          <span class="qw-btn" :class="{ spinning: refreshing }" title="刷新" @click="refresh">
            <Icon name="sidebar-sync" :size="16" />
          </span>
          <span
            class="qw-btn qw-tint"
            :title="`配色：${tintLabel()}（点击切换）`"
            @click="cycleTint"
          >
            <i class="qw-tint-dot" :class="'dot-' + tint"></i>
          </span>
          <span
            class="qw-btn"
            :class="{ active: pinned }"
            :title="pinned ? '取消置顶' : '窗口置顶'"
            v-if="inPywebview"
            @click="togglePin"
          >
            <Icon :name="pinned ? 'countdown-pinned' : 'countdown-unpinned'" :size="16" />
          </span>
          <span class="qw-btn qw-zoom" v-if="inPywebview && store.user" title="缩小（或 Ctrl+滚轮）" @click="zoom(-1)">−</span>
          <span class="qw-btn qw-zoom" v-if="inPywebview && store.user" title="放大（或 Ctrl+滚轮）" @click="zoom(1)">＋</span>
          <span class="qw-btn" v-if="inPywebview" title="最小化" @click="minimizeWindow">
            <Icon name="small-triangle-down" :size="16" />
          </span>
          <span class="qw-btn qw-close" v-if="inPywebview" title="关闭" @click="closeWindow">
            <Icon name="close" :size="16" />
          </span>
        </div>
      </div>

      <!-- 未登录：不单独登录，提示去主界面（点击打开主窗口） -->
      <div v-if="!store.user" class="qw-login-hint">
        <Icon name="user-icon" :size="30" />
        <div class="qw-login-title">请先登录流光</div>
        <div class="qw-login-sub">登录后此处展示四象限任务</div>
        <button class="qw-login-btn" @click="openMainWindow">打开主界面登录</button>
      </div>

      <div v-else class="qw-grid">
        <div
          v-for="q in QUADRANTS"
          :key="q.key"
          class="qw-quadrant"
          :class="{ 'drag-over': dragOverKey === q.key }"
          @dragover.prevent="onQuadDragOver($event, q)"
          @dragleave="dragOverKey === q.key && (dragOverKey = null)"
          @drop.prevent="onQuadDrop($event, q)"
          @dblclick="onDblClick(q)"
        >
          <div class="qw-quadrant-header">
            <span class="qw-dot" :style="{ background: q.color }"></span>
            <h3 :style="{ color: q.color }">{{ q.title }}</h3>
            <span class="qw-add" title="添加任务" @click.stop="onDblClick(q)"><Icon name="add" :size="16" /></span>
          </div>

          <div class="qw-tasklist">
            <div v-for="sec in tasksOfQuadrant(q)" :key="sec.name" class="qw-section">
              <div class="qw-section-header">
                <h6>{{ sec.name }}</h6>
                <span>{{ sec.tasks.length }}</span>
              </div>
              <div
                v-for="t in sec.tasks"
                :key="t.id"
                class="qw-task"
                draggable="true"
                @dragstart="onTaskDragStart($event, t)"
                @dragend="onTaskDragEnd"
                @click="openDetail($event, t)"
              >
                <span class="qw-check" :style="{ color: priColor(t.priority) }" @click.stop="toggleTask(t)">
                  <Icon name="calendar-checkbox" :size="16" />
                </span>
                <span class="qw-task-title">{{ t.title }}</span>
                <span class="qw-task-tips">
                  <span v-if="getProject(t.projectId)" class="qw-project">{{ getProject(t.projectId).emoji }}</span>
                  <span v-if="t.dueDate" class="qw-date" :class="{ overdue: isOverdue(t) }">{{ dueLabel(t) }}</span>
                </span>
              </div>
            </div>
            <div v-if="!tasksOfQuadrant(q).length" class="qw-empty">暂无任务</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 窗口边缘/角落缩放手柄（@mousedown.stop 防御性阻断可能的窗口级 mousedown 监听） -->
    <template v-if="inPywebview">
      <div
        v-for="edge in RESIZE_EDGES"
        :key="edge"
        class="qw-rh"
        :class="'rh-' + edge"
        :style="{ cursor: EDGE_CURSORS[edge] }"
        @pointerdown="onResizeDown($event, edge)"
        @mousedown.stop
      ></div>
    </template>

    <QuickAdd v-if="store.quickAdd.open" />
    <TaskDetail v-if="detailTask" :task="detailTask" />
    <div class="global-toast" v-if="store.toast">{{ store.toast }}</div>
  </div>
</template>

<style scoped>
.qw-root {
  height: 100%;
  width: 100%;
  padding: 8px;
  display: flex;
}
.qw-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* 透明窗口下不能用 backdrop-filter（global.css 已全局禁用），底色靠 --glass-panel-bg */
  background: var(--glass-panel-bg);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow);
}

/* 头部即窗口拖动区（pywebview easy_drag 按住空白处拖动） */
.qw-header {
  height: 36px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px 0 12px;
  color: var(--grey-60);
  cursor: move;
}
.qw-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--front-color);
}
.qw-count {
  font-size: 12px;
  color: var(--grey-40);
}
.qw-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
}
.qw-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--grey-60);
}
.qw-btn:hover {
  background: var(--grey-5);
  color: var(--front-color);
}
.qw-close:hover {
  color: var(--warn-red);
}
.qw-btn.active {
  color: var(--primary-color);
}
.qw-btn.spinning {
  animation: qw-spin 0.8s linear infinite;
}
@keyframes qw-spin {
  to { transform: rotate(360deg); }
}
/* 缩放按钮：用文字符号（图标库无 +/- 图标） */
.qw-zoom {
  font-size: 17px;
  line-height: 1;
  font-weight: 500;
  padding-bottom: 2px;
  box-sizing: border-box;
}

/* 配色按钮：色点显示当前档位（玻璃白 / 主题色 / 暗色） */
.qw-tint-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1px solid var(--grey-20);
  box-sizing: border-box;
}
.qw-tint-dot.dot-none {
  background: #fff;
}
.qw-tint-dot.dot-theme {
  background: var(--primary-color);
  border-color: var(--primary-color);
}
.qw-tint-dot.dot-dark {
  background: #24262d;
  border-color: #24262d;
}

/* ---------- 配色档位 ---------- */
/* 主题色轻染：面板与主色 14% 混合，随主题色联动 */
.qw-root.tint-theme .qw-panel {
  background: color-mix(in srgb, var(--primary-color) 14%, rgba(255, 255, 255, 0.9));
  border-color: color-mix(in srgb, var(--primary-color) 28%, transparent);
}
.qw-root.tint-theme .qw-quadrant {
  background: color-mix(in srgb, var(--primary-color) 7%, rgba(255, 255, 255, 0.45));
  border-color: color-mix(in srgb, var(--primary-color) 14%, rgba(255, 255, 255, 0.4));
}
/* 暗色：覆盖浅色文字/分隔色变量（global.css 的 grey 系为深字色） */
.qw-root.tint-dark {
  --front-color: #e8eaf0;
  --grey-60: #a6acba;
  --grey-40: #828896;
  --grey-30: #6a707c;
  --grey-5: rgba(255, 255, 255, 0.07);
  --grey-4: rgba(255, 255, 255, 0.09);
}
.qw-root.tint-dark .qw-panel {
  background: rgba(24, 26, 32, 0.88);
  border-color: rgba(255, 255, 255, 0.09);
  color: #e8eaf0;
}
.qw-root.tint-dark .qw-quadrant {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.07);
}
.qw-root.tint-dark .qw-quadrant.drag-over {
  background: rgba(255, 255, 255, 0.1);
}
.qw-root.tint-dark .qw-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

/* 未登录提示卡 */
.qw-login-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--grey-60);
  padding: 0 20px 16px;
}
.qw-login-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--front-color);
}
.qw-login-sub {
  font-size: 12px;
  color: var(--grey-40);
}
.qw-login-btn {
  margin-top: 10px;
  height: 34px;
  padding: 0 22px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--primary-color) 35%, transparent);
}
.qw-login-btn:hover {
  filter: brightness(1.06);
}

.qw-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 8px;
  padding: 4px 10px 10px;
  min-height: 0;
}
.qw-quadrant {
  background: rgba(255, 255, 255, 0.5);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.45);
  transition: box-shadow 0.18s var(--ease-spring), border-color 0.18s var(--ease-spring), background 0.18s;
}
.qw-quadrant.drag-over {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.7);
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--primary-color) 55%, transparent);
}
.qw-quadrant-header {
  height: 30px;
  flex: none;
  display: flex;
  align-items: center;
  padding: 0 8px;
}
.qw-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex: none;
  margin-right: 6px;
}
.qw-quadrant-header h3 {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qw-add {
  cursor: pointer;
  color: var(--grey-60);
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px;
  border-radius: 5px;
  display: inline-flex;
}
.qw-add:hover {
  background: var(--grey-5);
}
.qw-quadrant:hover .qw-add {
  opacity: 1;
}

.qw-tasklist {
  flex: 1;
  overflow-y: auto;
  padding: 0 0 4px;
}
.qw-section-header {
  display: flex;
  align-items: baseline;
  padding: 4px 10px 0;
}
.qw-section-header h6 {
  font-size: 11px;
  font-weight: 600;
  color: var(--grey-60);
}
.qw-section-header span {
  font-size: 11px;
  color: var(--grey-40);
  margin-left: 6px;
}

.qw-task {
  display: flex;
  align-items: center;
  height: 30px;
  line-height: 30px;
  padding: 0 10px 0 8px;
  cursor: pointer;
}
.qw-task:hover {
  background: var(--grey-4);
}
.qw-check {
  display: inline-flex;
  align-items: center;
  margin-right: 8px;
  cursor: pointer;
  flex: none;
}
.qw-task-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.qw-task-tips {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  flex: none;
}
.qw-project {
  font-size: 12px;
}
.qw-date {
  font-size: 11px;
  color: var(--grey-40);
  white-space: nowrap;
}
.qw-date.overdue {
  color: var(--warn-red);
}
.qw-empty {
  text-align: center;
  color: var(--grey-30);
  font-size: 11px;
  padding: 14px 0;
}

/* ---------- 窗口缩放手柄：压住窗口边/角并盖过面板边缘（qw-root 8px padding + 面板边），
   保证用户按视觉上的面板边缘/角落拖动即缩放；角落手柄后渲染覆盖边手柄 ---------- */
.qw-rh {
  position: fixed;
  z-index: 20;
  touch-action: none; /* 保证 pointer capture 不被浏览器手势打断 */
  user-select: none;
}
.rh-n, .rh-s { left: 20px; right: 20px; height: 12px; }
.rh-n { top: 0; }
.rh-s { bottom: 0; }
.rh-e, .rh-w { top: 20px; bottom: 20px; width: 12px; }
.rh-e { right: 0; }
.rh-w { left: 0; }
.rh-ne, .rh-nw, .rh-se, .rh-sw { width: 20px; height: 20px; }
.rh-ne { top: 0; right: 0; }
.rh-nw { top: 0; left: 0; }
.rh-se { bottom: 0; right: 0; }
.rh-sw { bottom: 0; left: 0; }
</style>
