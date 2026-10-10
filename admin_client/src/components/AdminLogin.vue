<script setup>
import { ref } from 'vue';
import { api } from '../api.js';

const emit = defineEmits(['logged-in']);

const username = ref('');
const password = ref('');
const error = ref('');
const submitting = ref(false);

async function submit() {
  if (submitting.value) return;
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码';
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    const data = await api.login(username.value.trim(), password.value);
    emit('logged-in', data.user);
  } catch (e) {
    error.value = e?.data?.error || '登录失败';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3l7 3v5c0 4.4-3 8.4-7 9.5C8 19.4 5 15.4 5 11V6l7-3z" />
          <circle cx="12" cy="10.2" r="1.6" />
          <path d="M12 11.8v3" />
        </svg>
      </div>
      <div class="login-title">流光 · 管理端</div>
      <div class="login-sub">用户管理 · 仅限管理员账户</div>

      <form class="login-form" @submit.prevent="submit">
        <label class="field">
          <span class="field-label">管理员用户名</span>
          <input v-model="username" class="g-input" type="text" autocomplete="username" placeholder="请输入管理员用户名" autofocus />
        </label>
        <label class="field">
          <span class="field-label">密码</span>
          <input v-model="password" class="g-input" type="password" autocomplete="current-password" placeholder="请输入密码" />
        </label>

        <div class="login-error" v-if="error">{{ error }}</div>

        <button class="g-btn login-btn" type="submit" :disabled="submitting">
          {{ submitting ? '登录中…' : '登 录' }}
        </button>

        <div class="login-hint">管理端仅对服务器白名单 IP 开放（LIUG_ADMIN_ALLOWED_IPS）</div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
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
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3), 0 8px 24px rgba(74, 108, 247, 0.35);
}
.login-title {
  margin-top: 16px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.06em;
}
.login-sub {
  margin-top: 6px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--grey-40);
  margin-bottom: 26px;
}
.login-form { width: 100%; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.field-label { font-size: 12px; color: var(--grey-60); }
.login-error {
  width: 100%;
  background: rgba(224, 49, 49, 0.1);
  color: #d9544d;
  border-radius: 10px;
  font-size: 12px;
  padding: 9px 12px;
  margin-bottom: 14px;
}
.login-btn { width: 100%; height: 42px; font-size: 15px; }
.login-hint {
  margin-top: 18px;
  font-size: 12px;
  color: var(--grey-40);
  text-align: center;
}
</style>
