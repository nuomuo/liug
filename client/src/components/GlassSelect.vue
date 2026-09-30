<script setup>
import { ref, computed, nextTick } from 'vue';
import { placeDropdown } from '../store.js';
import Icon from './Icon.vue';

// 多根组件：$attrs（class/style/@click.stop 等）透传给触发按钮
defineOptions({ inheritAttrs: false });

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label, dot? }]，dot 为选项色点
  placeholder: { type: String, default: '请选择' },
});
const emit = defineEmits(['update:modelValue']);

const triggerEl = ref(null);
const popEl = ref(null);
const open = ref(false);

const current = computed(() => props.options.find((o) => o.value === props.modelValue));

async function toggle() {
  if (open.value) close();
  else await openMenu();
}
async function openMenu() {
  open.value = true;
  await nextTick();
  if (popEl.value) placeDropdown(popEl.value, triggerEl.value);
}
function close() {
  open.value = false;
}
function pick(o) {
  emit('update:modelValue', o.value);
  close();
}

defineExpose({ close });
</script>

<template>
  <button ref="triggerEl" type="button" class="gs-trigger" :class="{ open }" v-bind="$attrs" @click="toggle">
    <span v-if="current?.dot" class="gs-dot" :style="{ background: current.dot }"></span>
    <span class="gs-label">{{ current?.label ?? placeholder }}</span>
    <Icon name="down-arrow" :size="12" class="gs-arrow" :class="{ open }" />
  </button>

  <!-- 玻璃风格下拉弹层 -->
  <Teleport to="body">
    <template v-if="open">
      <div class="gs-backdrop" @mousedown="close" @contextmenu.prevent="close"></div>
      <div ref="popEl" class="gs-pop" @mousedown.stop @contextmenu.prevent>
        <div
          v-for="o in options"
          :key="o.value"
          class="gs-option"
          :class="{ active: o.value === modelValue }"
          @click="pick(o)"
        >
          <span v-if="o.dot" class="gs-dot" :style="{ background: o.dot }"></span>
          <span class="gs-option-label">{{ o.label }}</span>
          <Icon v-if="o.value === modelValue" name="right-panel-all-selected" :size="13" class="gs-check" />
        </div>
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
/* 触发按钮 */
.gs-trigger {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  max-width: 160px;
  padding: 0 8px;
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.55);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
  color: var(--grey-80);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s var(--ease-spring);
}
.gs-trigger:hover,
.gs-trigger.open {
  border-color: var(--primary-color);
  background: rgba(255, 255, 255, 0.75);
}
.gs-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.gs-arrow {
  flex: none;
  color: var(--grey-40);
  transition: transform 0.2s var(--ease-spring);
}
.gs-trigger.open .gs-arrow,
.gs-arrow.open {
  transform: rotate(180deg);
}
.gs-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 弹层 */
.gs-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1390;
}
.gs-pop {
  position: fixed;
  z-index: 1400;
  min-width: 120px;
  max-height: 320px;
  overflow-y: auto;
  padding: 5px;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  animation: gs-in 0.2s var(--ease-spring);
  user-select: none;
}
@keyframes gs-in {
  from {
    opacity: 0;
    transform: translateY(-5px) scale(0.97);
    filter: blur(4px);
  }
  to {
    opacity: 1;
    transform: none;
    filter: blur(0);
  }
}
.gs-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: var(--radius-control);
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
  white-space: nowrap;
}
.gs-option:hover {
  background: rgba(255, 255, 255, 0.5);
}
.gs-option.active {
  color: var(--primary-color);
  font-weight: 500;
  background: rgba(255, 255, 255, 0.65);
}
.gs-option-label {
  flex: 1;
}
.gs-check {
  color: var(--primary-color);
}
</style>
