<script setup>
// 通用玻璃弹层：标题 + 内容插槽 + 取消/确认；danger 控制确认按钮配色
defineProps({
  title: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  danger: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
});
const emit = defineEmits(['confirm', 'close']);
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="!loading && emit('close')">
      <div class="modal-card">
        <div class="modal-title">{{ title }}</div>
        <div class="modal-body"><slot /></div>
        <div class="modal-actions">
          <button class="g-btn ghost" :disabled="loading" @click="emit('close')">取消</button>
          <button class="g-btn" :class="{ danger }" :disabled="loading" @click="emit('confirm')">
            {{ loading ? '处理中…' : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(20, 22, 30, 0.32);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fade-in 0.18s ease-out;
}
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.modal-card {
  width: 400px;
  max-width: 94vw;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 20px;
  box-shadow: var(--glass-shadow-float);
  padding: 22px 24px;
  animation: card-in 0.22s var(--ease-spring);
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to { opacity: 1; transform: none; }
}
.modal-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 14px;
}
.modal-body {
  font-size: 13px;
  color: var(--grey-80);
  line-height: 1.7;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
</style>
