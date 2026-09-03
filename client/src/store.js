import { reactive, computed } from 'vue';
import { api, setUnauthorizedHandler } from './api.js';

export const store = reactive({
  // 认证状态
  authReady: false, // 是否已完成首次会话检查
  user: null, // 当前登录用户 { id, username, role }
  loginError: '',

  loading: true,
  projects: [],
  folders: [],
  tasks: [],
  subtasks: [],
  countdowns: [],

  // 视图状态
  view: 'calendar', // calendar | list | matrix | focus | habit | countdown
  calendarViewMode: 'month', // month | week
  currentDate: new Date(),
  calendarSettings: {
    showCompleted: true,
  },

  // 日历筛选
  selectedProjectIds: [], // 空数组 = 全部
  selectedTag: '',

  // 弹层
  quickAdd: { open: false, presetDate: null, presetTask: null },
  detailTaskId: null,
  detailAnchor: null, // { x, y } 点击位置，详情就地弹出
  searchOpen: false,
  settingsOpen: false,

  toast: '',
});

export function showToast(msg, ms = 2200) {
  store.toast = msg;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => (store.toast = ''), ms);
}

// ---------- 认证 ----------
/** 清空本地数据（登出/会话失效时） */
function clearUserData() {
  store.projects = [];
  store.folders = [];
  store.tasks = [];
  store.subtasks = [];
  store.countdowns = [];
  store.loading = true;
  store.view = 'calendar';
  store.selectedProjectIds = [];
  store.selectedTag = '';
  store.detailTaskId = null;
  store.searchOpen = false;
  store.settingsOpen = false;
  store.quickAdd = { open: false, presetDate: null, presetTask: null };
}

/** 应用启动时检查会话；已登录则直接加载数据 */
export async function checkAuth() {
  try {
    const { user } = await api.me();
    store.user = user;
    if (user) await loadBootstrap();
  } catch {
    store.user = null;
  } finally {
    store.authReady = true;
  }
}

export async function login(username, password) {
  store.loginError = '';
  try {
    const { user } = await api.login(username, password);
    store.user = user;
    await loadBootstrap();
    return true;
  } catch (e) {
    store.loginError = e?.data?.error || '登录失败，请检查用户名和密码';
    return false;
  }
}

export async function logout() {
  try {
    await api.logout();
  } catch {}
  store.user = null;
  clearUserData();
}

/** 会话中途失效（API 返回 401）：回到登录页 */
setUnauthorizedHandler(() => {
  store.user = null;
  clearUserData();
  showToast('登录状态已失效，请重新登录');
});

export async function loadBootstrap() {
  const data = await api.bootstrap();
  store.projects = data.projects;
  store.folders = data.folders;
  store.tasks = data.tasks;
  store.subtasks = data.subtasks;
  store.countdowns = data.countdowns || [];
  store.loading = false;
  return data;
}

/** 打开任务详情：就地弹层（记住点击位置） */
export function openTaskDetail(task, x, y) {
  store.detailTaskId = task.id;
  store.detailAnchor = { x, y };
}
export function closeTaskDetail() {
  store.detailTaskId = null;
  store.detailAnchor = null;
}

export const projectMap = computed(() => {
  const m = new Map();
  for (const p of store.projects) m.set(p.id, p);
  return m;
});

export function getProject(id) {
  return projectMap.value.get(id);
}

export const allTags = computed(() => {
  const s = new Set();
  for (const t of store.tasks) for (const tag of t.tags) s.add(tag);
  return [...s].sort((a, b) => a.localeCompare(b, 'zh'));
});

export function subtasksOf(taskId) {
  return store.subtasks.filter((t) => t.parentId === taskId);
}

/** 日历筛选：按清单勾选 + 标签 */
export function calendarVisible(task) {
  if (store.selectedProjectIds.length && !store.selectedProjectIds.includes(task.projectId)) return false;
  if (store.selectedTag && !task.tags.includes(store.selectedTag)) return false;
  return true;
}

// ---------- 主题颜色 ----------
const THEME_KEY = 'dida-clone-theme-color';

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}
function mix(rgb, target, ratio) {
  return rgb.map((v, i) => Math.round(v + (target[i] - v) * ratio));
}
export function shade(hex, ratio) {
  const rgb = hexToRgb(hex);
  const target = ratio >= 0 ? [255, 255, 255] : [0, 0, 0];
  const out = mix(rgb, target, Math.abs(ratio));
  return '#' + out.map((v) => v.toString(16).padStart(2, '0')).join('');
}

/** 应用主题色到 CSS 变量并持久化（与原版 primary/hover/active 三态一致） */
export function applyTheme(color) {
  const root = document.documentElement;
  root.style.setProperty('--primary-color', color);
  root.style.setProperty('--primary-hover-color', shade(color, 0.15));
  root.style.setProperty('--primary-active-color', shade(color, -0.15));
  // 四周衍生色：左侧图标栏深色背景（ 即主色加深 20% ）
  root.style.setProperty('--left-sidebar-bg', shade(color, -0.2));
  // 页面背景照片整体着色，随主题色联动
  const [r, g, b] = hexToRgb(color);
  root.style.setProperty('--screen-tint', `rgba(${r}, ${g}, ${b}, 0.12)`);
  localStorage.setItem(THEME_KEY, color);
}
export function loadTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved) applyTheme(saved);
}

// ---------- 下拉菜单定位 ----------
/**
 * 将 fixed 定位的下拉菜单放到触发元素旁边（在触发位置弹出）
 * @param {HTMLElement} menuEl 菜单元素（已渲染）
 * @param {HTMLElement} triggerEl 触发元素
 * @param {{align?: 'left'|'right', offsetY?: number}} opts
 */
export function placeDropdown(menuEl, triggerEl, opts = {}) {
  // v-for 内的模板 ref 会被收集为数组，取第一个
  if (Array.isArray(menuEl)) menuEl = menuEl[0];
  if (!menuEl || !triggerEl) return;
  const { align = 'left', offsetY = 6 } = opts;
  const r = triggerEl.getBoundingClientRect();
  menuEl.style.left = 'auto';
  menuEl.style.top = 'auto';
  menuEl.style.right = 'auto';
  const w = menuEl.offsetWidth;
  const h = menuEl.offsetHeight;
  let left = align === 'right' ? r.right - w : r.left;
  let top = r.bottom + offsetY;
  // 越界翻转：右缘 → 向左收；下缘 → 向上翻
  if (left + w > window.innerWidth - 8) left = Math.max(8, r.right - w);
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - offsetY);
  menuEl.style.left = left + 'px';
  menuEl.style.top = top + 'px';
}

// ---------- 任务操作 ----------
/** 北京时间（UTC+8）本地时刻 ISO 字符串，与后端/CSV 导入口径一致 */
export function nowBeijingIso() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().replace('Z', '');
}

export const taskDrag = { id: null };
export function startTaskDrag(task, e) {
  taskDrag.id = task.id;
  if (e && e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(task.id));
  }
}
export function endTaskDrag() {
  taskDrag.id = null;
}

export async function toggleTask(task) {
  const done = task.status === 2;
  const patch = { status: done ? 0 : 2 };
  if (done) patch.completedAt = null;
  else patch.completedAt = nowBeijingIso();
  Object.assign(task, await api.updateTask(task.id, patch));
  for (const st of store.subtasks.filter((s) => s.parentId === task.id)) {
    Object.assign(st, await api.updateTask(st.id, patch));
  }
}

export async function updateTaskLocal(task, patch) {
  Object.assign(task, await api.updateTask(task.id, patch));
}

export async function deleteTaskLocal(task) {
  await api.deleteTask(task.id);
  store.tasks = store.tasks.filter((t) => t.id !== task.id);
  store.subtasks = store.subtasks.filter((t) => t.parentId !== task.id);
  if (store.detailTaskId === task.id) closeTaskDetail();
}

export async function addTask(payload) {
  const t = await api.createTask(payload);
  if (t.parentId) store.subtasks.push(t);
  else store.tasks.push(t);
  return t;
}

// ---------- 日期工具 ----------
export function fmtDate(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export function fmtTime(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 解析本地 ISO 字符串 'YYYY-MM-DDTHH:mm:ss' */
export function parseLocal(iso) {
  if (!iso) return null;
  return new Date(iso.slice(0, 10) + 'T' + (iso.slice(11, 19) || '00:00:00'));
}

export function dateKey(iso) {
  return iso ? iso.slice(0, 10) : null;
}

/** 任务落在某天的判定（含跨天任务） */
export function taskOnDay(task, ymd) {
  if (!task.startDate) return false;
  const s = task.startDate.slice(0, 10);
  const e = (task.dueDate || task.startDate).slice(0, 10);
  return ymd >= s && ymd <= e;
}

export function taskTimeLabel(task) {
  if (task.isAllDay) return '';
  const s = parseLocal(task.startDate);
  if (!s) return '';
  return fmtTime(s);
}
