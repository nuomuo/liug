<script setup>
import { computed } from 'vue';
import { store, showToast, logout } from '../store.js';
import Icon from './Icon.vue';

const railItems = [
  { key: 'calendar', icon: 'calendar-sidebar', label: '日历' },
  { key: 'list', icon: 'list-sidebar', label: '任务' },
  { key: 'matrix', icon: 'matrix-sidebar', label: '四象限' },
  // { key: 'focus', icon: 'sidebar-focus-sidebar', label: '专注' },
  // { key: 'habit', icon: 'habit-sidebar', label: '习惯' },
  { key: 'countdown', icon: 'countdown-sidebar', label: '倒数日' },
];

// 首字母头像（Contacts 风格：主题色渐变 + 首字符）
const initial = computed(() => (store.user?.username || '?').slice(0, 1).toUpperCase());

function go(item) {
  store.view = item.key;
}
function openSearch() {
  store.searchOpen = true;
}
async function doLogout() {
  await logout();
  showToast('已退出登录');
}
</script>

<template>
  <div class="left-rail">
    <div class="t-user" :title="store.user ? `${store.user.username}（设置）` : '设置'" @click="store.settingsOpen = true">
      <span class="avatar">{{ initial }}</span>
    </div>

    <div class="rail-mid">
      <div
        v-for="item in railItems"
        :key="item.key"
        class="rail-item"
        :class="{ active: store.view === item.key }"
        :title="item.label"
        @click="go(item)"
      >
        <Icon :name="item.icon" :size="24" />
      </div>
      <div class="rail-item" title="搜索 (Ctrl+K)" @click="openSearch">
        <Icon name="search-sidebar" :size="24" />
      </div>
    </div>

    <div class="rail-bottom">
      <div class="rail-item" title="同步" @click="showToast('数据已同步（本地 SQLite）')">
        <Icon name="sidebar-sync" :size="24" />
      </div>
      <div class="rail-item" title="通知" @click="showToast('暂无新通知')">
        <Icon name="notification-sidebar" :size="24" />
      </div>
      <div class="rail-item" title="帮助" @click="showToast('帮助中心：查看 README.md')">
        <Icon name="question-sidebar" :size="24" />
      </div>
      <div class="rail-item" title="退出登录" @click="doLogout">
        <Icon name="setting-sidebar" :size="24" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.left-rail {
  width: 56px;
  flex: none;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0 14px;
  /* 深色玻璃：随主题色联动的暗色 + 模糊透出壁纸 */
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--left-sidebar-bg) 62%, transparent),
    color-mix(in srgb, var(--left-sidebar-bg) 48%, transparent)
  );
  -webkit-backdrop-filter: blur(28px) saturate(160%);
  backdrop-filter: blur(28px) saturate(160%);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  z-index: 5;
}
.t-user {
  width: 36px;
  height: 36px;
  margin-bottom: 14px;
  cursor: pointer;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25), 0 2px 8px rgba(0, 0, 0, 0.25);
  letter-spacing: 0;
}
.t-user:hover .avatar {
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.45), 0 2px 12px rgba(0, 0, 0, 0.3);
}
.rail-mid {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.rail-item {
  position: relative;
  width: 42px;
  height: 42px;
  margin: 3px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 13px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.55);
  transition: background 0.18s var(--ease-spring), color 0.18s var(--ease-spring), transform 0.1s ease-out;
}
.rail-item:hover {
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.08);
}
.rail-item:active {
  transform: scale(0.94);
}
.rail-item.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.18);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
}
.rail-bottom {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
}
</style>
