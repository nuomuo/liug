<script setup>
/* 新建用户弹层：自包含组件，通过 emits 与父级通信 */
import { ref } from 'vue';
import { api } from '../api';
import { showToast } from '../toast';

const emit = defineEmits(['close', 'created']);

const username = ref('');
const password = ref('');
const role = ref('user');
const busy = ref(false);

async function create() {
  const payload = {
    username: username.value.trim(),
    password: password.value,
    role: role.value,
  };
  busy.value = true;
  try {
    await api('POST', '/system/users', payload);
    showToast(`用户 ${payload.username} 创建成功`);
    emit('created');
  } catch (e) {
    showToast(e.message, true);
    busy.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @mousedown.self="emit('close')">
      <div class="card modal">
        <div class="modal-title">新建用户</div>
        <label class="field">
          <span class="field-label">用户名</span>
          <input v-model="username" type="text" placeholder="2-32 个字符，不含空白" />
        </label>
        <label class="field">
          <span class="field-label">初始密码</span>
          <input v-model="password" type="text" placeholder="至少 6 个字符" @keydown.enter="create" />
        </label>
        <label class="field">
          <span class="field-label">角色</span>
          <select v-model="role">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="btn" @click="emit('close')">取消</button>
          <button class="btn primary" :disabled="busy" @click="create">创建</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
