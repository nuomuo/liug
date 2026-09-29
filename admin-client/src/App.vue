<script setup>
import { onMounted, ref } from 'vue';
import { api } from './api';
import { showToast } from './toast';
import AppToast from './components/AppToast.vue';
import CreateUserModal from './components/CreateUserModal.vue';
import ResetPasswordModal from './components/ResetPasswordModal.vue';

let me = ref(null); // 当前登录的管理员
const users = ref([]);
const showCreate = ref(false);
const resetTarget = ref(null); // 正在重置密码的用户

// 登录表单
const loginUsername = ref('');
const loginPassword = ref('');
const loginError = ref('');
const loginBusy = ref(false);

function fmtTime(iso) {
  return iso ? String(iso).slice(0, 19).replace('T', ' ') : '-';
}

async function login() {
  loginError.value = '';
  loginBusy.value = true;
  try {
    const data = await api('POST', '/system/auth/login', {
      username: loginUsername.value.trim(),
      password: loginPassword.value,
    });
    me.value = data.user;
    loginPassword.value = '';
    await loadUsers();
  } catch (e) {
    loginError.value = e.message;
  } finally {
    loginBusy.value = false;
  }
}

async function logout() {
  try {
    await api('POST', '/system/auth/logout');
  } catch {}
  me.value = null;
}

async function loadUsers() {
  try {
    const data = await api('GET', '/system/users');
    users.value = data.users;
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      me.value = null;
    }
    showToast(e.message, true);
  }
}

// 角色切换：唯一管理员后端会拒绝；自己降级成功则回登录页
async function toggleRole(u) {
  try {
    await api('PUT', `/system/users/${u.id}`, { role: u.role === 'admin' ? 'user' : 'admin' });
    if (me.value && u.id === me.value.id && u.role === 'admin') {
      showToast('当前账户已降为普通用户');
      me.value = null;
      return;
    }
    await loadUsers();
  } catch (e) {
    showToast(e.message, true);
  }
}

// 禁用/启用：禁用自己成功则回登录页
async function toggleDisabled(u) {
  try {
    await api('PUT', `/system/users/${u.id}`, { disabled: !u.disabled });
    if (me.value && u.id === me.value.id && !u.disabled) {
      showToast('当前账户已被禁用');
      me.value = null;
      return;
    }
    await loadUsers();
  } catch (e) {
    showToast(e.message, true);
  }
}

function removeUser(u) {
  if (!confirm(`确定删除用户「${u.username}」？该用户的所有数据（清单/任务/倒数日）将被永久删除，且无法恢复。`)) return;
  api('DELETE', `/system/users/${u.id}`)
    .then(async () => {
      showToast(`用户 ${u.username} 已删除`);
      await loadUsers();
    })
    .catch((e) => showToast(e.message, true));
}

// 启动：已登录则直接进入管理页（沿用旧版逻辑）
onMounted(async () => {
  try {
    const data = await api('GET', '/system/auth/me');
    me.value = data.user;
    await loadUsers();
  } catch {}
});
</script>

<template>
  <!-- 登录 -->
  <div v-if="!me" class="login-wrap">
    <div class="card login-card">
      <div class="login-title">系统管理</div>
      <div class="login-sub">仅管理员可登录 · 用户管理</div>
      <label class="field">
        <span class="field-label">用户名</span>
        <input
          v-model="loginUsername"
          type="text"
          placeholder="管理员账户"
          autocomplete="username"
          @keydown.enter="login"
        />
      </label>
      <label class="field">
        <span class="field-label">密码</span>
        <input
          v-model="loginPassword"
          type="password"
          placeholder="密码"
          autocomplete="current-password"
          @keydown.enter="login"
        />
      </label>
      <button class="btn primary full" :disabled="loginBusy" @click="login">登录</button>
      <div class="login-error">{{ loginError }}</div>
    </div>
  </div>

  <!-- 用户管理 -->
  <div v-else class="admin-view">
    <div class="card page">
      <div class="page-header">
        <div class="page-title">
          <span>用户管理</span>
          <span v-if="users.length" class="count">{{ users.length }} 个账户</span>
        </div>
        <div class="header-right">
          <span class="me-name">{{ me.username }}</span>
          <button class="btn" @click="logout">退出</button>
          <button class="btn primary" @click="showCreate = true">＋ 新建用户</button>
        </div>
      </div>

      <div class="table-wrap">
        <table class="table">
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
            <tr v-for="u in users" :key="u.id" :class="{ off: u.disabled }">
              <td class="td-name">
                {{ u.username }}
                <span v-if="me && u.id === me.id" class="me-tag">当前账户</span>
              </td>
              <td>
                <span class="role-tag" :class="u.role">{{ u.role === 'admin' ? '管理员' : '普通用户' }}</span>
              </td>
              <td>
                <span class="status-dot" :class="u.disabled ? 'off' : 'on'"></span>{{ u.disabled ? '已禁用' : '正常' }}
              </td>
              <td class="td-time">{{ fmtTime(u.createdAt) }}</td>
              <td class="td-actions">
                <button class="btn" @click="resetTarget = u">重置密码</button>
                <button class="btn" @click="toggleRole(u)">{{ u.role === 'admin' ? '降为普通用户' : '设为管理员' }}</button>
                <button class="btn" @click="toggleDisabled(u)">{{ u.disabled ? '启用' : '禁用' }}</button>
                <button class="btn danger" @click="removeUser(u)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!users.length" class="empty">暂无用户</div>
      </div>
    </div>
  </div>

  <!-- 弹层（统一 Teleport 到 body） -->
  <CreateUserModal v-if="showCreate" @close="showCreate = false" @created="showCreate = false; loadUsers()" />
  <ResetPasswordModal v-if="resetTarget" :user="resetTarget" @close="resetTarget = null" />
  <AppToast />
</template>
