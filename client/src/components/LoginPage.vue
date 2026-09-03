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
        <Icon name="calendar-sidebar" :size="30" />
      </div>
      <div class="login-title">流光</div>
      <div class="login-sub">日历 · 清单 · 专注</div>

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
  background-image: linear-gradient(var(--screen-tint), var(--screen-tint)), url('/bg.jpg');
  background-size: cover;
  background-position: center;
}
.login-card {
  width: 380px;
  max-width: 92vw;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 28px;
  box-shadow: var(--glass-shadow-float);
  padding: 40px 38px 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: card-in 0.4s var(--ease-spring);
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(16px) scale(0.97); filter: blur(8px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.login-logo {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3), 0 8px 24px color-mix(in srgb, var(--primary-color) 35%, transparent);
}
.login-title {
  margin-top: 16px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--front-color);
}
.login-sub {
  margin-top: 6px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--grey-40);
  margin-bottom: 26px;
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
  height: 42px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: 12px;
  padding: 0 14px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.65);
}
.field input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 18%, transparent);
}
.login-error {
  width: 100%;
  background: rgba(224, 49, 49, 0.1);
  color: #d9544d;
  border-radius: 10px;
  font-size: 12px;
  padding: 9px 12px;
  margin-bottom: 14px;
}
.login-btn {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: filter 0.15s, transform 0.1s ease-out;
  box-shadow: 0 6px 18px color-mix(in srgb, var(--primary-color) 35%, transparent);
}
.login-btn:hover {
  filter: brightness(1.06);
}
.login-btn:active {
  transform: scale(0.98);
}
.login-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.login-hint {
  margin-top: 18px;
  font-size: 12px;
  color: var(--grey-40);
}
</style>
