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
import AdminPage from './components/AdminPage.vue';

const viewComponent = computed(() => {
  switch (store.view) {
    case 'list': return ListPage;
    case 'matrix': return MatrixPage;
    case 'focus': return FocusPage;
    case 'countdown': return CountdownPage;
    case 'habit': return PlaceholderPage;
    case 'admin': return AdminPage;
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
});
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));

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
  <LoginPage v-if="store.authReady && !store.user" />
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
  display: flex;
  overflow: hidden;
  /* 主题色着色层叠在原背景照片上，选主题色时四周同步变色 */
  background-image: linear-gradient(var(--screen-tint), var(--screen-tint)), url('/bg.png');
  background-size: cover;
  background-position: 0 100%;
}
.main-view {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
}
</style>
