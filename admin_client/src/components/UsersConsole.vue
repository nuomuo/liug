<script setup>
import { ref, onMounted } from 'vue';
import { api } from '../api.js';
import GlassModal from './GlassModal.vue';

const props = defineProps({ me: { type: Object, required: true } });
const emit = defineEmits(['logged-out']);

const users = ref([]);
const loading = ref(false);
const listError = ref('');

// 新增用户
const showCreate = ref(false);
const creating = ref(false);
const form = ref({ username: '', password: '', role: 'user' });
const createError = ref('');

// 重置密码
const resetTarget = ref(null);
const resetPassword = ref('');
const resetError = ref('');
const resetting = ref(false);

// 修改自己的密码
const showChangePwd = ref(false);
const changeForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' });
const changeError = ref('');
const changing = ref(false);

// 通用确认弹层（禁用/启用、角色切换、删除）
const confirmState = ref(null); // { title, message, confirmText, danger, run }
const confirming = ref(false);

async function refresh() {
  loading.value = true;
  listError.value = '';
  try {
    users.value = (await api.listUsers()).users;
  } catch (e) {
    listError.value = e?.data?.error || '加载用户列表失败';
  } finally {
    loading.value = false;
  }
}
onMounted(refresh);

const isSelf = (u) => u.id === props.me.id;

function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(String(ts).replace(' ', 'T') + 'Z'); // sqlite datetime('now') 存的是 UTC
  return isNaN(d.getTime()) ? ts : d.toLocaleString('zh-CN', { hour12: false });
}

/* ---------- 新增用户 ---------- */
function openCreate() {
  form.value = { username: '', password: '', role: 'user' };
  createError.value = '';
  showCreate.value = true;
}

async function submitCreate() {
  if (creating.value) return;
  const username = form.value.username.trim();
  if (!username) return (createError.value = '请输入用户名');
  if (form.value.password.length < 6) return (createError.value = '密码至少需要 6 个字符');
  creating.value = true;
  createError.value = '';
  try {
    await api.createUser({ username, password: form.value.password, role: form.value.role });
    showCreate.value = false;
    await refresh();
  } catch (e) {
    createError.value = e?.data?.error || '创建失败';
  } finally {
    creating.value = false;
  }
}

/* ---------- 重置密码 ---------- */
function openReset(u) {
  resetTarget.value = u;
  resetPassword.value = '';
  resetError.value = '';
}

async function submitReset() {
  if (resetting.value || !resetTarget.value) return;
  if (resetPassword.value.length < 6) return (resetError.value = '密码至少需要 6 个字符');
  resetting.value = true;
  resetError.value = '';
  try {
    await api.updateUser(resetTarget.value.id, { password: resetPassword.value });
    resetTarget.value = null;
    await refresh();
  } catch (e) {
    resetError.value = e?.data?.error || '重置失败';
  } finally {
    resetting.value = false;
  }
}

/* ---------- 修改自己的密码 ---------- */
function openChangePwd() {
  changeForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' };
  changeError.value = '';
  showChangePwd.value = true;
}

async function submitChangePwd() {
  if (changing.value) return;
  if (!changeForm.value.oldPassword) return (changeError.value = '请输入当前密码');
  if (changeForm.value.newPassword.length < 6) return (changeError.value = '新密码至少需要 6 个字符');
  if (changeForm.value.newPassword !== changeForm.value.confirmPassword) {
    return (changeError.value = '两次输入的新密码不一致');
  }
  changing.value = true;
  changeError.value = '';
  try {
    await api.changePassword(changeForm.value.oldPassword, changeForm.value.newPassword);
    showChangePwd.value = false;
  } catch (e) {
    changeError.value = e?.data?.error || '修改失败';
  } finally {
    changing.value = false;
  }
}

/* ---------- 确认类操作 ---------- */
function askToggleDisable(u) {
  const disabling = !u.disabled;
  confirmState.value = {
    title: disabling ? '禁用账户' : '启用账户',
    message: disabling
      ? `禁用后「${u.username}」将无法登录，已有会话立即失效。确定禁用？`
      : `确定启用账户「${u.username}」？`,
    confirmText: disabling ? '禁用' : '启用',
    danger: disabling,
    run: () => api.updateUser(u.id, { disabled: disabling }),
  };
}

function askToggleRole(u) {
  const toAdmin = u.role !== 'admin';
  confirmState.value = {
    title: toAdmin ? '设为管理员' : '设为普通用户',
    message: toAdmin
      ? `「${u.username}」将获得管理端完整权限（用户管理等）。确定？`
      : `「${u.username}」将失去管理员权限，无法再登录管理端。确定？`,
    confirmText: toAdmin ? '设为管理员' : '设为普通用户',
    danger: !toAdmin,
    run: () => api.updateUser(u.id, { role: toAdmin ? 'admin' : 'user' }),
  };
}

function askDelete(u) {
  confirmState.value = {
    title: '删除账户',
    message: `确定删除账户「${u.username}」？账户将被移除；其历史数据文件会保留在服务器上（不自动清理）。`,
    confirmText: '删除',
    danger: true,
    run: () => api.deleteUser(u.id),
  };
}

async function runConfirmed() {
  if (confirming.value || !confirmState.value) return;
  confirming.value = true;
  try {
    await confirmState.value.run();
    confirmState.value = null;
    await refresh();
  } catch (e) {
    confirmState.value = null;
    listError.value = e?.data?.error || '操作失败';
  } finally {
    confirming.value = false;
  }
}

async function logout() {
  try {
    await api.logout();
  } catch {}
  emit('logged-out');
}
</script>

<template>
  <div class="console">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-left">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3l7 3v5c0 4.4-3 8.4-7 9.5C8 19.4 5 15.4 5 11V6l7-3z" />
            <circle cx="12" cy="10.2" r="1.6" />
            <path d="M12 11.8v3" />
          </svg>
        </div>
        <div>
          <div class="brand-title">流光 LIUG · 用户管理</div>
          <div class="brand-sub">共 {{ users.length }} 个账户</div>
        </div>
      </div>
      <div class="topbar-right">
        <span class="who">{{ me.username }} · 管理员</span>
        <button class="g-btn ghost" @click="logout">退出登录</button>
      </div>
    </header>

    <!-- 用户面板 -->
    <section class="panel">
      <div class="panel-head">
        <div class="panel-title">账户列表</div>
        <button class="g-btn" @click="openCreate">＋ 新增用户</button>
      </div>

      <div class="list-error" v-if="listError">{{ listError }}</div>

      <div class="table-wrap">
        <table class="users-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>角色</th>
              <th>状态</th>
              <th>创建时间</th>
              <th class="th-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !users.length">
              <td colspan="5" class="empty">加载中…</td>
            </tr>
            <tr v-else-if="!users.length">
              <td colspan="5" class="empty">暂无账户</td>
            </tr>
            <tr v-for="u in users" :key="u.id" :class="{ off: u.disabled }">
              <td class="td-name">
                <span class="uname">{{ u.username }}</span>
                <span class="self-tag" v-if="isSelf(u)">当前账户</span>
              </td>
              <td><span class="pill" :class="u.role === 'admin' ? 'admin' : 'user'">{{ u.role === 'admin' ? '管理员' : '普通用户' }}</span></td>
              <td><span class="pill" :class="u.disabled ? 'off' : 'ok'">{{ u.disabled ? '已禁用' : '正常' }}</span></td>
              <td class="td-time">{{ fmtTime(u.createdAt) }}</td>
              <td class="td-actions">
                <template v-if="isSelf(u)">
                  <button class="link-btn" @click="openChangePwd">修改密码</button>
                </template>
                <template v-else>
                  <button class="link-btn danger" v-if="!u.disabled" @click="askToggleDisable(u)">禁用</button>
                  <button class="link-btn" v-else @click="askToggleDisable(u)">启用</button>
                  <button class="link-btn" @click="openReset(u)">重置密码</button>
                  <button class="link-btn" v-if="u.role !== 'admin'" @click="askToggleRole(u)">设为管理员</button>
                  <button class="link-btn warn" v-else @click="askToggleRole(u)">设为普通用户</button>
                  <button class="link-btn danger" @click="askDelete(u)">删除</button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 新增用户 -->
    <GlassModal
      v-if="showCreate"
      title="新增用户"
      confirm-text="创建"
      :loading="creating"
      @confirm="submitCreate"
      @close="showCreate = false"
    >
      <div class="form">
        <label class="form-field">
          <span class="form-label">用户名</span>
          <input v-model="form.username" class="g-input" type="text" placeholder="登录用户名（唯一）" />
        </label>
        <label class="form-field">
          <span class="form-label">初始密码</span>
          <input v-model="form.password" class="g-input" type="text" placeholder="至少 6 个字符" autocomplete="off" />
        </label>
        <div class="form-field">
          <span class="form-label">角色</span>
          <div class="seg">
            <button type="button" :class="{ on: form.role === 'user' }" @click="form.role = 'user'">普通用户</button>
            <button type="button" :class="{ on: form.role === 'admin' }" @click="form.role = 'admin'">管理员</button>
          </div>
        </div>
        <div class="form-error" v-if="createError">{{ createError }}</div>
      </div>
    </GlassModal>

    <!-- 重置密码 -->
    <GlassModal
      v-if="resetTarget"
      :title="`重置密码 · ${resetTarget.username}`"
      confirm-text="重置"
      :loading="resetting"
      @confirm="submitReset"
      @close="resetTarget = null"
    >
      <div class="form">
        <label class="form-field">
          <span class="form-label">新密码</span>
          <input v-model="resetPassword" class="g-input" type="text" placeholder="至少 6 个字符" autocomplete="off" @keydown.enter="submitReset" />
        </label>
        <div class="form-hint">重置后该用户所有已登录的会话将立即失效</div>
        <div class="form-error" v-if="resetError">{{ resetError }}</div>
      </div>
    </GlassModal>

    <!-- 修改自己的密码 -->
    <GlassModal
      v-if="showChangePwd"
      title="修改密码"
      confirm-text="修改"
      :loading="changing"
      @confirm="submitChangePwd"
      @close="showChangePwd = false"
    >
      <div class="form">
        <label class="form-field">
          <span class="form-label">当前密码</span>
          <input v-model="changeForm.oldPassword" class="g-input" type="password" placeholder="输入当前密码" autocomplete="current-password" />
        </label>
        <label class="form-field">
          <span class="form-label">新密码</span>
          <input v-model="changeForm.newPassword" class="g-input" type="password" placeholder="至少 6 个字符" autocomplete="new-password" />
        </label>
        <label class="form-field">
          <span class="form-label">确认新密码</span>
          <input v-model="changeForm.confirmPassword" class="g-input" type="password" placeholder="再次输入新密码" autocomplete="new-password" @keydown.enter="submitChangePwd" />
        </label>
        <div class="form-hint">修改后其他设备登录的会话将立即失效，当前管理端会话保持不变</div>
        <div class="form-error" v-if="changeError">{{ changeError }}</div>
      </div>
    </GlassModal>

    <!-- 通用确认 -->
    <GlassModal
      v-if="confirmState"
      :title="confirmState.title"
      :confirm-text="confirmState.confirmText"
      :danger="confirmState.danger"
      :loading="confirming"
      @confirm="runConfirmed"
      @close="confirmState = null"
    >
      {{ confirmState.message }}
    </GlassModal>
  </div>
</template>

<style scoped>
.console {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 20px 48px;
  animation: rise 0.35s var(--ease-spring);
}
@keyframes rise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: none; }
}

/* 顶栏 */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.topbar-left { display: flex; align-items: center; gap: 14px; }
.brand-logo {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3), 0 6px 18px rgba(74, 108, 247, 0.32);
}
.brand-title { font-size: 17px; font-weight: 700; letter-spacing: 0.02em; }
.brand-sub { margin-top: 2px; font-size: 12px; color: var(--grey-40); }
.topbar-right { display: flex; align-items: center; gap: 14px; }
.who { font-size: 13px; color: var(--grey-60); }

/* 面板 */
.panel {
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border);
  border-radius: 22px;
  box-shadow: var(--glass-shadow-float);
  padding: 20px 22px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.panel-title { font-size: 14px; font-weight: 700; }

.list-error {
  background: rgba(224, 49, 49, 0.1);
  color: #d9544d;
  border-radius: 10px;
  font-size: 12px;
  padding: 9px 12px;
  margin-bottom: 12px;
}

.table-wrap { overflow-x: auto; }
.users-table { width: 100%; border-collapse: collapse; }
.users-table th {
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--grey-40);
  padding: 8px 10px;
  border-bottom: 1px solid rgba(29, 29, 31, 0.08);
  white-space: nowrap;
}
.users-table td {
  padding: 12px 10px;
  font-size: 13px;
  border-bottom: 1px solid rgba(29, 29, 31, 0.05);
  vertical-align: middle;
}
.users-table tbody tr:last-child td { border-bottom: none; }
.users-table tbody tr:not(.off):hover td { background: rgba(255, 255, 255, 0.4); }
tr.off .uname { color: var(--grey-40); text-decoration: line-through; text-decoration-color: rgba(224, 49, 49, 0.5); }

.td-name { display: flex; align-items: center; gap: 8px; }
.uname { font-weight: 600; }
.self-tag {
  font-size: 11px;
  color: #3b5bdb;
  background: rgba(74, 108, 247, 0.12);
  border-radius: 6px;
  padding: 2px 7px;
}
.td-time { color: var(--grey-50); font-variant-numeric: tabular-nums; white-space: nowrap; }
.td-actions { white-space: nowrap; }
.th-actions { text-align: right; }
.td-actions { text-align: right; }
.empty { text-align: center; color: var(--grey-40); padding: 32px 0 !important; }

/* 表单 */
.form { display: flex; flex-direction: column; gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--grey-60); }
.form-hint { font-size: 12px; color: var(--grey-40); }
.form-error {
  background: rgba(224, 49, 49, 0.1);
  color: #d9544d;
  border-radius: 10px;
  font-size: 12px;
  padding: 8px 12px;
}
.seg {
  display: inline-flex;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: 10px;
  overflow: hidden;
  width: fit-content;
  background: rgba(255, 255, 255, 0.55);
}
.seg button {
  height: 34px;
  padding: 0 16px;
  font-size: 13px;
  color: var(--grey-60);
  transition: background 0.15s, color 0.15s;
}
.seg button.on {
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover-color));
  color: #fff;
  font-weight: 600;
}
</style>
