<script setup>
import { ref, onMounted } from 'vue';
import { api } from '../api.js';
import { store, showToast } from '../store.js';
import Icon from './Icon.vue';

const users = ref([]);
const loading = ref(false);

// 新建用户表单
const showCreate = ref(false);
const newUser = ref({ username: '', password: '', role: 'user' });
const creating = ref(false);

// 重置密码弹层
const resetTarget = ref(null); // 待重置密码的用户
const resetPassword = ref('');

// 操作中的用户 ID（按钮防抖）
const acting = ref('');

async function reload() {
  loading.value = true;
  try {
    const { users: list } = await api.listUsers();
    users.value = list;
  } catch (e) {
    showToast(e?.data?.error || '加载用户列表失败');
  } finally {
    loading.value = false;
  }
}
onMounted(reload);

async function createUser() {
  if (creating.value) return;
  creating.value = true;
  try {
    await api.createUser({ ...newUser.value });
    showToast(`用户 ${newUser.value.username} 创建成功`);
    showCreate.value = false;
    newUser.value = { username: '', password: '', role: 'user' };
    await reload();
  } catch (e) {
    showToast(e?.data?.error || '创建用户失败');
  } finally {
    creating.value = false;
  }
}

async function toggleDisabled(u) {
  acting.value = u.id;
  try {
    await api.updateUser(u.id, { disabled: !u.disabled });
    await reload();
  } catch (e) {
    showToast(e?.data?.error || '操作失败');
  } finally {
    acting.value = '';
  }
}

async function toggleRole(u) {
  acting.value = u.id;
  try {
    await api.updateUser(u.id, { role: u.role === 'admin' ? 'user' : 'admin' });
    await reload();
    // 当前用户自己被降级时，同步本地状态（侧边栏入口会消失）
    if (u.id === store.user?.id) {
      store.user = { ...store.user, role: u.role === 'admin' ? 'user' : 'admin' };
      if (store.user.role !== 'admin') store.view = 'calendar';
    }
  } catch (e) {
    showToast(e?.data?.error || '操作失败');
  } finally {
    acting.value = '';
  }
}

async function deleteUser(u) {
  if (!confirm(`确定删除用户「${u.username}」？该用户的所有数据（清单/任务/倒数日）将被永久删除，且无法恢复。`)) return;
  acting.value = u.id;
  try {
    await api.deleteUser(u.id);
    showToast(`用户 ${u.username} 已删除`);
    await reload();
  } catch (e) {
    showToast(e?.data?.error || '删除失败');
  } finally {
    acting.value = '';
  }
}

async function submitResetPassword() {
  if (!resetPassword.value || resetPassword.value.length < 6) {
    showToast('新密码至少需要 6 个字符');
    return;
  }
  try {
    await api.updateUser(resetTarget.value.id, { password: resetPassword.value });
    showToast(`已重置 ${resetTarget.value.username} 的密码`);
    resetTarget.value = null;
    resetPassword.value = '';
  } catch (e) {
    showToast(e?.data?.error || '重置密码失败');
  }
}

function fmtTime(iso) {
  return iso ? iso.slice(0, 19).replace('T', ' ') : '-';
}
</script>

<template>
  <div class="admin-page">
    <div class="admin-header">
      <div class="admin-title">
        <Icon name="user-icon" :size="20" />
        <span>用户管理</span>
        <span class="admin-count" v-if="users.length">{{ users.length }} 个账户</span>
      </div>
      <button class="btn primary" @click="showCreate = true">
        <Icon name="add" :size="14" /> 新建用户
      </button>
    </div>

    <div class="admin-table-wrap">
      <table class="admin-table" v-if="users.length">
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
          <tr v-for="u in users" :key="u.id" :class="{ me: u.id === store.user?.id, off: u.disabled }">
            <td class="td-name">
              {{ u.username }}
              <span class="me-tag" v-if="u.id === store.user?.id">当前账户</span>
            </td>
            <td>
              <span class="role-tag" :class="u.role">{{ u.role === 'admin' ? '管理员' : '普通用户' }}</span>
            </td>
            <td>
              <span class="status-dot" :class="u.disabled ? 'off' : 'on'"></span>
              {{ u.disabled ? '已禁用' : '正常' }}
            </td>
            <td class="td-time">{{ fmtTime(u.createdAt) }}</td>
            <td class="td-actions">
              <button class="btn small" @click="resetTarget = u">重置密码</button>
              <button class="btn small" @click="toggleRole(u)" :disabled="acting === u.id">
                {{ u.role === 'admin' ? '降为普通用户' : '设为管理员' }}
              </button>
              <button class="btn small" @click="toggleDisabled(u)" :disabled="acting === u.id">
                {{ u.disabled ? '启用' : '禁用' }}
              </button>
              <button class="btn small danger" @click="deleteUser(u)" :disabled="acting === u.id">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="admin-empty" v-else-if="!loading">暂无用户</div>
      <div class="admin-empty" v-else>加载中…</div>
    </div>

    <!-- 新建用户 -->
    <div class="modal-backdrop" v-if="showCreate" @mousedown.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">新建用户</div>
        <label class="field">
          <span class="field-label">用户名</span>
          <input v-model="newUser.username" type="text" placeholder="2-32 个字符，不含空白" />
        </label>
        <label class="field">
          <span class="field-label">初始密码</span>
          <input v-model="newUser.password" type="text" placeholder="至少 6 个字符" />
        </label>
        <label class="field">
          <span class="field-label">角色</span>
          <select v-model="newUser.role">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn primary" @click="createUser" :disabled="creating">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 重置密码 -->
    <div class="modal-backdrop" v-if="resetTarget" @mousedown.self="resetTarget = null">
      <div class="modal">
        <div class="modal-title">重置密码 — {{ resetTarget.username }}</div>
        <label class="field">
          <span class="field-label">新密码</span>
          <input v-model="resetPassword" type="text" placeholder="至少 6 个字符" @keyup.enter="submitResetPassword" />
        </label>
        <div class="modal-actions">
          <button class="btn" @click="resetTarget = null">取消</button>
          <button class="btn primary" @click="submitResetPassword">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-page {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 24px 28px;
  background: var(--glass-panel-bg);
  -webkit-backdrop-filter: var(--glass-panel-blur);
  backdrop-filter: var(--glass-panel-blur);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
  margin: 10px;
}
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.admin-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--front-color);
}
.admin-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--grey-40);
  margin-left: 4px;
}
.admin-table-wrap {
  border: 1px solid var(--glass-border-soft);
  border-radius: 14px;
  overflow: hidden auto;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--front-color);
}
.admin-table th {
  text-align: left;
  font-weight: 600;
  color: var(--grey-40);
  padding: 10px 14px;
  border-bottom: 1px solid var(--grey-5);
  background: rgba(255, 255, 255, 0.7);
  white-space: nowrap;
}
.admin-table td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--grey-3);
  vertical-align: middle;
}
.admin-table tr:last-child td {
  border-bottom: none;
}
.admin-table tbody tr {
  transition: background 0.2s var(--ease-spring);
}
.admin-table tbody tr:hover td {
  background: rgba(255, 255, 255, 0.5);
}
tr.me td {
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
}
.admin-table tbody tr.me:hover td {
  background: color-mix(in srgb, var(--primary-color) 7%, rgba(255, 255, 255, 0.5));
}
tr.off td {
  opacity: 0.55;
}
.td-name {
  font-weight: 600;
}
.me-tag {
  font-size: 11px;
  font-weight: 400;
  color: var(--primary-color);
  border: 1px solid color-mix(in srgb, var(--primary-color) 35%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  border-radius: 999px;
  padding: 1px 7px;
  margin-left: 8px;
}
.role-tag {
  font-size: 12px;
  border-radius: 999px;
  padding: 2px 9px;
}
.role-tag.admin {
  color: #b8860b;
  background: rgba(184, 134, 11, 0.12);
}
.role-tag.user {
  color: var(--grey-60);
  background: var(--grey-5);
}
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.status-dot.on {
  background: #46c793;
}
.status-dot.off {
  background: #d9544d;
}
.td-time {
  color: var(--grey-40);
  font-size: 12px;
  white-space: nowrap;
}
.td-actions {
  white-space: nowrap;
  text-align: right;
}
.th-actions {
  text-align: right;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--glass-border-soft);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
  color: var(--grey-80);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s var(--ease-spring);
}
.btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.7);
}
.btn.primary {
  background: var(--primary-color);
  border-color: transparent;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 2px 8px color-mix(in srgb, var(--primary-color) 35%, transparent);
  color: #fff;
}
.btn.primary:hover {
  background: var(--primary-hover-color);
  color: #fff;
}
.btn.small {
  height: 26px;
  padding: 0 11px;
  margin-left: 6px;
}
.btn.danger:hover {
  border-color: #d9544d;
  color: #d9544d;
  background: rgba(217, 84, 77, 0.08);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.admin-empty {
  padding: 40px;
  text-align: center;
  color: var(--grey-40);
  font-size: 13px;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1600;
  background: rgba(15, 18, 30, 0.18);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: 380px;
  max-width: 92vw;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  padding: 22px 24px;
  animation: modal-materialize 0.24s var(--ease-spring);
}
@keyframes modal-materialize {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--front-color);
  margin-bottom: 16px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 13px;
}
.field-label {
  font-size: 12px;
  color: var(--grey-60);
}
.field input,
.field select {
  height: 36px;
  border: 1px solid rgba(29, 29, 31, 0.12);
  border-radius: var(--radius-control);
  padding: 0 11px;
  font-size: 13px;
  outline: none;
  color: var(--front-color);
  background: rgba(255, 255, 255, 0.6);
  transition: border-color 0.2s var(--ease-spring), background 0.2s var(--ease-spring);
}
.field input:focus,
.field select:focus {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.8);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
</style>
