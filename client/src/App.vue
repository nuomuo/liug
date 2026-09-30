<script setup>
import { onMounted, onBeforeUnmount, computed } from 'vue';
import { store, checkAuth, loadBootstrap, showToast, loadTheme, closeTaskDetail } from './store.js';
import LeftRail from './components/LeftRail.vue';
import CalendarPage from './components/CalendarPage.vue';
import ListPage from './components/ListPage.vue';
import MatrixPage from './components/MatrixPage.vue';
import FocusPage from './components/FocusPage.vue';
import CountdownPage from './components/CountdownPage.vue';
import PlaceholderPage from './components/PlaceholderPage.vue';
import QuickAdd from './components/QuickAdd.vue';
import TaskDetail from './components/TaskDetail.vue';
import SearchOverlay from './components/SearchOverlay.vue';
import SettingsPanel from './components/SettingsPanel.vue';
import LoginPage from './components/LoginPage.vue';
import QuadrantWidget from './components/QuadrantWidget.vue';

// 桌面四象限小组件：/quadrant 路径渲染独立小组件页（无左侧栏，透明背景）
const isWidget = window.location.pathname.startsWith('/quadrant');

const viewComponent = computed(() => {
  switch (store.view) {
    case 'list': return ListPage;
    case 'matrix': return MatrixPage;
    case 'focus': return FocusPage;
    case 'countdown': return CountdownPage;
    case 'habit': return PlaceholderPage;
    default: return CalendarPage;
  }
});

const detailTask = computed(() => {
  if (store.detailTaskId == null) return null;
  return (
    store.tasks.find((t) => t.id === store.detailTaskId) ||
    store.subtasks.find((t) => t.id === store.detailTaskId) ||
    null
  );
});

// 主界面数据刷新：窗口聚焦 / 页面重新可见 / 30s 轮询兜底 / 跨窗口 storage 事件。
// 桌面小组件（独立窗口）上增删改任务或登录后打点 liug-sync，主界面立即拉取最新数据；
// 任何弹窗（快速添加/任务详情/搜索/设置）打开时跳过，避免自动刷新打断正在进行的编辑。
let refreshDebounce = null;
let pollTimer = null;
function scheduleRefresh() {
  clearTimeout(refreshDebounce);
  refreshDebounce = setTimeout(async () => {
    if (!store.user || document.hidden) return;
    if (store.quickAdd.open || store.detailTaskId != null || store.searchOpen || store.settingsOpen) return;
    try {
      await loadBootstrap();
    } catch (e) {
      /* 静默失败：不打断当前使用 */
    }
  }, 250);
}
function onVisibilityChange() {
  if (!document.hidden) scheduleRefresh();
}
// storage 事件只在「其他同源窗口」写入时触发（桌面小组件 → 主界面），不会自我循环
function onStorage(e) {
  if (e.key === 'liug-sync') scheduleRefresh();
}

onMounted(async () => {
  loadTheme();
  await checkAuth();
  if (store.user && store.loading) {
    // checkAuth 内 loadBootstrap 失败时的兜底
    try {
      await loadBootstrap();
    } catch (e) {
      showToast('加载失败：无法连接后端服务');
    }
  }
  window.addEventListener('keydown', onKey);
  if (!isWidget) {
    window.addEventListener('focus', scheduleRefresh);
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisibilityChange);
    pollTimer = setInterval(() => {
      if (!document.hidden) scheduleRefresh();
    }, 30000);
  }
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey);
  window.removeEventListener('focus', scheduleRefresh);
  window.removeEventListener('storage', onStorage);
  document.removeEventListener('visibilitychange', onVisibilityChange);
  clearInterval(pollTimer);
  clearTimeout(refreshDebounce);
});

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    store.searchOpen = true;
  }
  if (e.key === 'Escape') {
    if (store.searchOpen) store.searchOpen = false;
    else if (store.settingsOpen) store.settingsOpen = false;
    else if (store.quickAdd.open) store.quickAdd.open = false;
    else if (store.detailTaskId != null) closeTaskDetail();
  }
}
</script>

<template>
  <!-- 小组件模式未登录时也交给 QuadrantWidget：显示「去主界面登录」提示卡，不渲染完整登录页 -->
  <LoginPage v-if="store.authReady && !store.user && !isWidget" />
  <QuadrantWidget v-else-if="isWidget && store.authReady" />
  <div class="app-shell" id="container-main" v-else-if="store.authReady">
    <LeftRail />
    <component :is="viewComponent" class="main-view" />
    <QuickAdd v-if="store.quickAdd.open" />
    <TaskDetail v-if="detailTask" :task="detailTask" />
    <SearchOverlay v-if="store.searchOpen" />
    <SettingsPanel v-if="store.settingsOpen" />
    <div class="global-toast" v-if="store.toast">{{ store.toast }}</div>
  </div>
</template>

<style scoped>
.app-shell {
  height: 100%;
  width: 100%;
  display: flex;
  overflow: hidden;
  /* 壁纸 + 主题色着色层已挂在 body（global.css），保证铺满整个视口 */
}
.main-view {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
}
</style>
