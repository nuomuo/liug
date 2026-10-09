<script setup>
// 玻璃风格百分比滑杆（替代原生 range 的默认观感）：拖动实时 emit，松手时额外 emit change
const props = defineProps({
  modelValue: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  step: { type: Number, default: 1 },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue', 'change']);

function ratio() {
  const span = props.max - props.min;
  if (!span) return 0;
  const r = (props.modelValue - props.min) / span;
  return Math.max(0, Math.min(1, r));
}
function onInput(e) {
  emit('update:modelValue', Number(e.target.value));
}
function onChange(e) {
  emit('change', Number(e.target.value));
}
</script>

<template>
  <input
    class="range-slider"
    type="range"
    :min="min"
    :max="max"
    :step="step"
    :value="modelValue"
    :disabled="disabled"
    :style="{ '--range-pct': (ratio() * 100) + '%' }"
    @input="onInput"
    @change="onChange"
  />
</template>

<style scoped>
.range-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 22px;
  background: transparent;
  outline: none;
  cursor: pointer;
}
.range-slider::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    var(--primary-color) 0,
    var(--primary-color) var(--range-pct, 0%),
    rgba(29, 29, 31, 0.12) var(--range-pct, 0%),
    rgba(29, 29, 31, 0.12) 100%
  );
  box-shadow: inset 0 0 0 1px rgba(29, 29, 31, 0.06);
}
.range-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  margin-top: -5px;
  border-radius: 50%;
  background: #fff;
  border: 1px solid var(--glass-border);
  box-shadow: 0 1px 4px rgba(20, 20, 40, 0.28);
  transition: transform 0.12s var(--ease-spring), box-shadow 0.12s var(--ease-spring);
}
.range-slider:hover::-webkit-slider-thumb {
  transform: scale(1.12);
}
.range-slider:active::-webkit-slider-thumb {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--primary-color) 18%, transparent);
}
.range-slider::-moz-range-track {
  height: 6px;
  border-radius: 999px;
  background: rgba(29, 29, 31, 0.12);
}
.range-slider::-moz-range-progress {
  height: 6px;
  border-radius: 999px;
  background: var(--primary-color);
}
.range-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  border: 1px solid var(--glass-border);
  box-shadow: 0 1px 4px rgba(20, 20, 40, 0.28);
}
.range-slider:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
