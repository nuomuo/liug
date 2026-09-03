<script setup>
import { store, showToast, logout } from '../store.js';
import Icon from './Icon.vue';
import avatarUrl from '../assets/avatar-new.png';

const railItems = [
  { key: 'list', icon: 'list-sidebar', label: '任务' },
  { key: 'calendar', icon: 'calendar-sidebar', label: '日历' },
  { key: 'matrix', icon: 'matrix-sidebar', label: '四象限' },
  { key: 'focus', icon: 'sidebar-focus-sidebar', label: '专注' },
  { key: 'habit', icon: 'habit-sidebar', label: '习惯' },
  { key: 'countdown', icon: 'countdown-sidebar', label: '倒数日' },
];

function go(item) {
  store.view = item.key;
}
function openSearch() {
  store.searchOpen = true;
}
function goAdmin() {
  store.view = 'admin';
}
async function doLogout() {
  await logout();
  showToast('已退出登录');
}
</script>

<template>
  <div class="left-rail">
    <div class="t-user" :title="store.user ? `${store.user.username}（设置）` : '设置'" @click="store.settingsOpen = true">
      <img class="avatar" :src="avatarUrl" alt="" />
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
        <Icon :name="item.icon" :size="28" />
      </div>
      <div class="rail-item" title="搜索 (Ctrl+K)" @click="openSearch">
        <Icon name="search-sidebar" :size="28" />
      </div>
      <div
        v-if="store.user?.role === 'admin'"
        class="rail-item"
        :class="{ active: store.view === 'admin' }"
        title="用户管理"
        @click="goAdmin"
      >
        <Icon name="user-icon" :size="28" />
      </div>
    </div>

    <div class="rail-bottom">
      <div class="rail-item" title="同步" @click="showToast('数据已同步（本地 SQLite）')">
        <Icon name="sidebar-sync" :size="28" />
      </div>
      <div class="rail-item" title="通知" @click="showToast('暂无新通知')">
        <Icon name="notification-sidebar" :size="28" />
      </div>
      <div class="rail-item" title="帮助" @click="showToast('帮助中心：查看 README.md')">
        <Icon name="question-sidebar" :size="28" />
      </div>
      <div class="rail-item" title="退出登录" @click="doLogout">
        <Icon name="setting-sidebar" :size="28" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.left-rail {
  width: 50px;
  flex: none;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0 11px;
  /* 深色底由主题色加深派生，随设置面板选色联动 */
  background: color-mix(in srgb, var(--left-sidebar-bg) 82%, transparent);
  z-index: 5;
}
.t-user {
  width: 32px;
  height: 32px;
  margin-bottom: 11px;
  cursor: pointer;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: block;
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
  width: 40px;
  height: 40px;
  margin: 5px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  color: #fff;
  opacity: 0.4;
  transition: opacity 0.15s, background 0.15s;
}
.rail-item:hover {
  opacity: 0.6;
}
.rail-item.active {
  opacity: 1;
}
.rail-item.active::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: #fff;
}
.rail-bottom {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
}
</style>
