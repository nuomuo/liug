<script setup>
import { ref, onMounted } from 'vue';
import { api } from './api.js';
import AdminLogin from './components/AdminLogin.vue';
import UsersConsole from './components/UsersConsole.vue';

// 启动时探测会话：已是管理员会话直接进控制台，否则进独立登录页
const me = ref(null);
const booting = ref(true);

onMounted(async () => {
  try {
    me.value = (await api.me()).user;
  } catch {
    me.value = null;
  }
  booting.value = false;
});
</script>

<template>
  <div v-if="booting" class="boot">正在加载管理端…</div>
  <AdminLogin v-else-if="!me" @logged-in="(u) => (me = u)" />
  <UsersConsole v-else :me="me" @logged-out="me = null" />
</template>

<style scoped>
.boot {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--grey-40);
  font-size: 13px;
}
</style>
