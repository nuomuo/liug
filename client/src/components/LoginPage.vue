<script setup>
import { ref, onMounted } from 'vue';
import { store, login, loginLocal, loginRemote } from '../store.js';
import { api } from '../api.js';
import Icon from './Icon.vue';

const username = ref('');
const password = ref('');
const submitting = ref(false);

// 桌面本地服务（有 /api/desktop/config 端点；远程服务端 404 → 走普通账号登录表单）
const isLocalDesktop = ref(false);
const remoteInput = ref('');
const showRemote = ref(false);
const remoteError = ref('');
const remoteSaving = ref(false);

onMounted(async () => {
  try {
    const cfg = await api.getDesktopConfig();
    isLocalDesktop.value = true;
    remoteInput.value = cfg.remoteUrl || '';
  } catch {
    /* 远程浏览器环境：保持账号密码登录表单 */
  }
});

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

async function useLocal() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await loginLocal();
  } finally {
    submitting.value = false;
  }
}

/** 登录云端账号：本地代理登录远程服务器，数据落在本地镜像库并双向同步 */
async function connectRemote() {
  const url = remoteInput.value.trim().replace(/\/+$/, '');
  if (!/^https?:\/\/.+/.test(url)) {
    remoteError.value = '请输入服务器地址，形如 https://example.com';
    return;
  }
  if (!username.value.trim() || !password.value) {
    remoteError.value = '请输入用户名和密码';
    return;
  }
  remoteSaving.value = true;
  remoteError.value = '';
  store.loginError = '';
  try {
    await api.saveDesktopConfig(url); // 记住服务器地址，下次预填
    const ok = await loginRemote(url, username.value.trim(), password.value);
    if (!ok) remoteError.value = store.loginError || '登录失败';
  } catch (e) {
    remoteError.value = e?.data?.error || '登录失败';
  } finally {
    remoteSaving.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <Icon name="calendar-sidebar" :size="30" />
      </div>
      <div class="login-title">流光</div>
      <div class="login-sub">日历 · 清单 · 专注</div>

      <!-- 桌面本地：单机使用（免登录）/ 登录云端账号 双入口 -->
      <template v-if="isLocalDesktop">
        <button class="login-btn" :disabled="submitting" @click="useLocal">
          {{ submitting ? '进入中…' : '单机使用（免登录）' }}
        </button>
        <div class="local-hint">数据仅保存在本机，不同步任何服务器</div>

        <div class="divider"><span>或</span></div>

        <button class="ghost-btn" @click="showRemote = !showRemote">登录账号（云端同步）</button>
        <div class="remote-form" v-if="showRemote">
          <input
            v-model="remoteInput"
            type="url"
            placeholder="服务器地址，如 https://example.com"
          />
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="用户名"
          />
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="密码"
            @keydown.enter="connectRemote"
          />
          <div class="login-error" v-if="remoteError">{{ remoteError }}</div>
          <button class="ghost-btn primary" :disabled="remoteSaving" @click="connectRemote">
            {{ remoteSaving ? '登录中…' : '登录' }}
          </button>
          <div class="remote-hint">断网时仍可使用本地数据，联网后自动双向同步</div>
        </div>
      </template>

      <!-- 账号密码登录（远程浏览器环境） -->
      <form v-else class="login-form" @submit.prevent="submit">
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

/* ---------- 桌面本地：单机/云端双入口 ---------- */
.local-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--grey-40);
}
.divider {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 18px 0;
  color: var(--grey-40);
  font-size: 12px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--glass-border);
}
.ghost-btn {
  width: 100%;
  height: 42px;
  border: 1px solid rgba(29, 29, 31, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  color: var(--grey-80);
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.ghost-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.72);
}
.ghost-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.ghost-btn.primary {
  border: none;
  color: #fff;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  box-shadow: 0 6px 18px color-mix(in srgb, var(--primary-color) 35%, transparent);
}
.remote-form {
  width: 100%;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.remote-form input {
  height: 42px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: 12px;
  padding: 0 14px;
  font-size: 13px;
  outline: none;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.65);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.remote-form input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 18%, transparent);
}
.remote-hint {
  font-size: 12px;
  color: var(--grey-40);
  text-align: center;
}
</style>
