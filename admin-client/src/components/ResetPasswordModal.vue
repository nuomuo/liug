<script setup>
/* 重置密码弹层：通过 props 接收目标用户，emits 通知父级 */
import { ref } from 'vue';
import { api } from '../api';
import { showToast } from '../toast';

const props = defineProps({ user: { type: Object, required: true } });
const emit = defineEmits(['close']);

const password = ref('');

async function submit() {
  if (!password.value || password.value.length < 6) {
    showToast('新密码至少需要 6 个字符', true);
    return;
  }
  try {
    const data = await api('PUT', `/system/users/${props.user.id}`, { password: password.value });
    showToast(`已重置 ${data.user.username} 的密码`);
    emit('close');
  } catch (e) {
    showToast(e.message, true);
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @mousedown.self="emit('close')">
      <div class="card modal">
        <div class="modal-title">重置密码 — {{ user.username }}</div>
        <label class="field">
          <span class="field-label">新密码</span>
          <input v-model="password" type="text" placeholder="至少 6 个字符" @keydown.enter="submit" />
        </label>
        <div class="modal-actions">
          <button class="btn" @click="emit('close')">取消</button>
          <button class="btn primary" @click="submit">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
