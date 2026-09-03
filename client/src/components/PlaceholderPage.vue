<script setup>
import { computed } from 'vue';
import { store } from '../store.js';
import Icon from './Icon.vue';

const meta = computed(() => {
  switch (store.view) {
    case 'habit': return { icon: 'habit-sidebar', title: '习惯', desc: '习惯打卡模块规划中，当前版本聚焦日历与任务管理' };
    case 'countdown': return { icon: 'countdown-sidebar', title: '倒数日', desc: '倒数日模块规划中，可在日历中查看节日与纪念日' };
    default: return { icon: 'calendar-sidebar', title: '敬请期待', desc: '' };
  }
});
</script>

<template>
  <div class="placeholder-page">
    <div class="pp-card">
      <Icon :name="meta.icon" :size="52" />
      <h2>{{ meta.title }}</h2>
      <p>{{ meta.desc }}</p>
    </div>
  </div>
</template>

<style scoped>
.placeholder-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
}
.pp-card {
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  padding: 50px 70px;
  text-align: center;
  color: var(--grey-30);
}
.pp-card .icon {
  opacity: 0.35;
}
.pp-card h2 {
  margin-top: 14px;
  font-size: 18px;
  color: var(--grey-60);
}
.pp-card p {
  margin-top: 8px;
  font-size: 13px;
}
</style>
