<script setup>
import { ref, computed } from 'vue';
import { store, applyTheme, showToast, logout } from '../store.js';
import { api } from '../api.js';
import Icon from './Icon.vue';

const presets = [
  { name: '黑海（默认）', color: '#484553' },
  { name: '墨绿', color: '#0c9e6e' },
  { name: '深海蓝', color: '#2f6fe4' },
  { name: '赤陶', color: '#d9544d' },
  { name: '暖橙', color: '#e8852c' },
  { name: '紫罗兰', color: '#8b6ff0' },
  { name: '青碧', color: '#0caeae' },
  { name: '樱花粉', color: '#e06a9f' },
];

const currentColor = ref(getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#484553');

function pick(color) {
  currentColor.value = color;
  applyTheme(color);
  showToast('主题颜色已更新');
}
function reset() {
  pick('#484553');
}

// ---------- 账户：修改密码 / 退出登录 ----------
const showPwdForm = ref(false);
const pwdForm = ref({ oldPassword: '', newPassword: '', confirm: '' });
const pwdError = ref('');
const pwdSaving = ref(false);

const accountName = computed(() => store.user?.username || '未登录');
const accountRole = computed(() =>
  store.user ? (store.user.role === 'admin' ? '管理员' : '普通用户') : ''
);

function togglePwdForm() {
  showPwdForm.value = !showPwdForm.value;
  pwdError.value = '';
  pwdForm.value = { oldPassword: '', newPassword: '', confirm: '' };
}

async function submitPassword() {
  const { oldPassword, newPassword, confirm } = pwdForm.value;
  if (!oldPassword || !newPassword) {
    pwdError.value = '请填写原密码和新密码';
    return;
  }
  if (newPassword.length < 6) {
    pwdError.value = '新密码至少需要 6 个字符';
    return;
  }
  if (newPassword !== confirm) {
    pwdError.value = '两次输入的新密码不一致';
    return;
  }
  pwdSaving.value = true;
  try {
    await api.changePassword(oldPassword, newPassword);
    showToast('密码修改成功');
    togglePwdForm();
  } catch (e) {
    pwdError.value = e?.data?.error || '密码修改失败';
  } finally {
    pwdSaving.value = false;
  }
}

async function doLogout() {
  store.settingsOpen = false;
  await logout();
  showToast('已退出登录');
}
</script>

<template>
  <div class="settings-backdrop" @mousedown.self="store.settingsOpen = false">
    <div class="settings-panel" @mousedown.stop>
      <div class="sp-header">
        <div class="sp-user">
          <span class="sp-avatar">{{ (store.user?.username || 'U').slice(0,1).toUpperCase() }}</span>
          <div class="sp-user-info">
            <div class="sp-name">{{ accountName }}</div>
            <div class="sp-sub">{{ accountRole }} · 数据独立存储于个人 SQLite 数据库</div>
          </div>
        </div>
        <span class="sp-close" @click="store.settingsOpen = false"><Icon name="close" :size="16" /></span>
      </div>

      <div class="sp-body">
        <div class="sp-section">
          <div class="sp-section-title">账户</div>
          <div class="account-actions">
            <button class="account-btn" @click="togglePwdForm">
              {{ showPwdForm ? '取消修改' : '修改密码' }}
            </button>
            <button class="account-btn logout" @click="doLogout">退出登录</button>
          </div>
          <div class="pwd-form" v-if="showPwdForm">
            <label class="pwd-field">
              <span>原密码</span>
              <input type="password" v-model="pwdForm.oldPassword" autocomplete="current-password" />
            </label>
            <label class="pwd-field">
              <span>新密码</span>
              <input type="password" v-model="pwdForm.newPassword" autocomplete="new-password" />
            </label>
            <label class="pwd-field">
              <span>确认新密码</span>
              <input type="password" v-model="pwdForm.confirm" autocomplete="new-password" @keyup.enter="submitPassword" />
            </label>
            <div class="pwd-error" v-if="pwdError">{{ pwdError }}</div>
            <button class="pwd-submit" @click="submitPassword" :disabled="pwdSaving">
              {{ pwdSaving ? '保存中…' : '保存新密码' }}
            </button>
          </div>
        </div>

        <div class="sp-section">
          <div class="sp-section-title">主题颜色</div>
          <div class="sp-section-desc">应用于按钮、选中态与高亮元素，立即生效并自动保存</div>
          <div class="swatch-grid">
            <div
              v-for="p in presets"
              :key="p.color"
              class="swatch"
              :class="{ active: currentColor === p.color }"
              :title="p.name"
              @click="pick(p.color)"
            >
              <span class="swatch-color" :style="{ background: p.color }">
                <Icon v-if="currentColor === p.color" name="right-panel-all-selected" :size="12" />
              </span>
              <span class="swatch-name">{{ p.name }}</span>
            </div>
          </div>

          <div class="custom-row">
            <label class="custom-label">
              <input type="color" :value="currentColor" @input="pick($event.target.value)" />
              <span>自定义颜色</span>
            </label>
            <span class="custom-value">{{ currentColor }}</span>
            <button class="reset-btn" @click="reset">恢复默认</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1500;
  background: rgba(15, 18, 30, 0.18);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.settings-panel {
  width: 460px;
  max-width: 92vw;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow-float);
  overflow: hidden;
  animation: pop-in 0.22s var(--ease-spring);
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); filter: blur(6px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.sp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--grey-5);
}
.sp-user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sp-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0;
  color: #fff;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25), 0 2px 8px rgba(20, 20, 40, 0.18);
}
.sp-name {
  font-size: 16px;
  font-weight: 600;
}
.sp-sub {
  font-size: 12px;
  color: var(--grey-40);
  margin-top: 3px;
}
.sp-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--grey-40);
  border-radius: 50%;
  transition: background 0.15s var(--ease-spring), color 0.15s var(--ease-spring);
}
.sp-close:hover {
  background: rgba(29, 29, 31, 0.06);
  color: var(--front-color);
}
.sp-body {
  padding: 14px 20px 20px;
}
.sp-section + .sp-section {
  margin-top: 22px;
}
.sp-section-title {
  font-size: 14px;
  font-weight: 600;
}
.sp-section-desc {
  font-size: 12px;
  color: var(--grey-40);
  margin-top: 3px;
}
.swatch-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 14px;
}
.swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 8px 4px;
  border-radius: var(--radius-control);
  transition: background 0.15s var(--ease-spring), box-shadow 0.15s var(--ease-spring);
}
.swatch:hover {
  background: rgba(255, 255, 255, 0.5);
}
.swatch.active {
  background: rgba(255, 255, 255, 0.55);
  box-shadow: inset 0 0 0 1px var(--glass-border);
}
.swatch-color {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.25);
}
.swatch-name {
  font-size: 12px;
  color: var(--grey-60);
}
.custom-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--grey-5);
}
.custom-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
}
.custom-label input[type='color'] {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: none;
  padding: 0;
}
.custom-value {
  font-size: 12px;
  color: var(--grey-40);
  font-family: monospace;
  flex: 1;
}
.reset-btn {
  height: 28px;
  padding: 0 14px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.55);
  font-size: 12px;
  color: var(--grey-80);
  cursor: pointer;
  transition: all 0.15s var(--ease-spring);
}
.reset-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.75);
}
.account-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
.account-btn {
  height: 32px;
  padding: 0 16px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.55);
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
  transition: all 0.15s var(--ease-spring);
}
.account-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.75);
}
.account-btn.logout:hover {
  border-color: rgba(217, 84, 77, 0.45);
  color: #d9544d;
  background: rgba(217, 84, 77, 0.08);
}
.pwd-form {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--grey-5);
}
.pwd-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 11px;
}
.pwd-field span {
  font-size: 12px;
  color: var(--grey-60);
}
.pwd-field input {
  height: 34px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  padding: 0 11px;
  font-size: 13px;
  outline: none;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.6);
  transition: border-color 0.15s var(--ease-spring), box-shadow 0.15s var(--ease-spring);
}
.pwd-field input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 18%, transparent);
}
.pwd-error {
  font-size: 12px;
  color: #d9544d;
  background: rgba(217, 84, 77, 0.1);
  border-radius: var(--radius-control);
  padding: 7px 10px;
  margin-bottom: 11px;
}
.pwd-submit {
  height: 34px;
  width: 100%;
  border: none;
  border-radius: var(--radius-control);
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--primary-color) 30%, transparent);
  transition: filter 0.15s var(--ease-spring);
}
.pwd-submit:hover {
  filter: brightness(1.06);
}
.pwd-submit:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
