<script setup>
import { ref } from 'vue';
import { store, login } from '../store.js';
import Icon from './Icon.vue';

const username = ref('');
const password = ref('');
const submitting = ref(false);

async function submit() {
  if (submitting.value) return;
  if (!username.value.trim() || !password.value) {
    store.loginError = '请输入用户名和密码';
    return;
  }
  submitting.value = true;
  try {
    await login(username.value.trim(), password.value);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-logo">
        <Icon name="calendar-sidebar" :size="34" />
      </div>
      <div class="login-title">滴答清单</div>
      <div class="login-sub">多用户版 · 请登录你的账户</div>

      <label class="field">
        <span class="field-label">用户名</span>
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          placeholder="请输入用户名"
          autofocus
        />
      </label>
      <label class="field">
        <span class="field-label">密码</span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        />
      </label>

      <div class="login-error" v-if="store.loginError">{{ store.loginError }}</div>

      <button class="login-btn" type="submit" :disabled="submitting">
        {{ submitting ? '登录中…' : '登 录' }}
      </button>

      <div class="login-hint">忘记密码？请联系管理员重置</div>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background-image: linear-gradient(var(--screen-tint), var(--screen-tint)), url('/bg.png');
  background-size: cover;
  background-position: 0 100%;
}
.login-card {
  width: 360px;
  max-width: 92vw;
  background: #fff;
  border-radius: 14px;
  box-shadow: var(--default-shadow);
  padding: 36px 34px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.login-logo {
  width: 60px;
  height: 60px;
  border-radius: 16px;
  background: var(--primary-color);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-title {
  margin-top: 14px;
  font-size: 20px;
  font-weight: 700;
  color: var(--front-color);
}
.login-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--grey-40);
  margin-bottom: 22px;
}
.field {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.field-label {
  font-size: 12px;
  color: var(--grey-60);
}
.field input {
  height: 40px;
  border: 1px solid var(--grey-20);
  border-radius: 8px;
  padding: 0 12px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
  color: var(--front-color);
  background: #fff;
}
.field input:focus {
  border-color: var(--primary-color);
}
.login-error {
  width: 100%;
  background: #fdecec;
  color: #d9544d;
  border-radius: 8px;
  font-size: 12px;
  padding: 8px 12px;
  margin-bottom: 14px;
}
.login-btn {
  width: 100%;
  height: 40px;
  border: none;
  border-radius: 8px;
  background: var(--primary-color);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s;
}
.login-btn:hover {
  background: var(--primary-hover-color);
}
.login-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.login-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--grey-40);
}
</style>
