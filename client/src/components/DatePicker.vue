<script setup>
import { ref, computed, nextTick } from 'vue';
import { fmtDate, placeDropdown } from '../store.js';
import { dayInfo, WEEKDAY_LABELS } from '../lib/lunar.js';
import Icon from './Icon.vue';

// 多根组件：$attrs（class/title/@click.stop 等）透传给触发输入框
defineOptions({ inheritAttrs: false });

const props = defineProps({
  modelValue: { type: String, default: '' }, // 'YYYY-MM-DD'，空串表示无日期
});
const emit = defineEmits(['update:modelValue']);

const inputEl = ref(null);
const popEl = ref(null);
const open = ref(false);
const view = ref(new Date()); // 弹层显示的月份游标
const todayStr = fmtDate(new Date());

const cells = computed(() => {
  const y = view.value.getFullYear();
  const m = view.value.getMonth();
  const lead = (new Date(y, m, 1).getDay() + 6) % 7; // 周一=0
  const start = new Date(y, m, 1 - lead);
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
});
const title = computed(() => `${view.value.getFullYear()}年${view.value.getMonth() + 1}月`);

async function openPicker() {
  open.value = true;
  view.value = props.modelValue ? new Date(props.modelValue + 'T00:00:00') : new Date();
  await nextTick();
  if (popEl.value) placeDropdown(popEl.value, inputEl.value);
}
function close() {
  open.value = false;
}
function step(n) {
  const d = new Date(view.value);
  d.setMonth(d.getMonth() + n);
  view.value = d;
}
function pick(d) {
  emit('update:modelValue', fmtDate(d));
  close();
}
function clearDate() {
  emit('update:modelValue', '');
  close();
}

defineExpose({ close });
</script>

<template>
  <input
    ref="inputEl"
    type="date"
    class="dp-input"
    v-bind="$attrs"
    :value="modelValue"
    readonly
    @mousedown.prevent="openPicker"
  />

  <!-- 玻璃风格日期弹层（替代原生 date picker） -->
  <Teleport to="body">
    <template v-if="open">
      <div class="dp-backdrop" @mousedown="close" @contextmenu.prevent="close"></div>
      <div ref="popEl" class="dp-pop" @mousedown.stop @contextmenu.prevent>
        <div class="dp-head">
          <span class="dp-title">{{ title }}</span>
          <span class="dp-btns">
            <a class="dp-btn" title="上个月" @click="step(-1)"><Icon name="kalendae-chevron-left" :size="14" /></a>
            <a class="dp-btn" title="今天" @click="pick(new Date())"><span class="dp-today-dot"></span></a>
            <a class="dp-btn" title="下个月" @click="step(1)"><Icon name="kalendae-chevron-right" :size="14" /></a>
          </span>
        </div>
        <div class="dp-week">
          <span v-for="(w, i) in WEEKDAY_LABELS" :key="i" class="dp-w" :class="{ dim: i >= 5 }">{{ w }}</span>
        </div>
        <div class="dp-grid">
          <span v-for="d in cells" :key="fmtDate(d)" class="dp-cell">
            <span
              class="dp-day"
              :class="{
                out: d.getMonth() !== view.getMonth(),
                sel: fmtDate(d) === modelValue,
                today: fmtDate(d) === todayStr,
              }"
              @click="pick(d)"
            >
              <span class="dp-num">
                {{ d.getDate() }}
                <span v-if="dayInfo(d).isHoliday" class="dp-flag"><Icon name="calendar-holiday" :size="10" /></span>
                <span v-else-if="dayInfo(d).isWork" class="dp-flag work">班</span>
              </span>
              <i class="dp-lunar">{{ dayInfo(d).festival || dayInfo(d).label }}</i>
            </span>
          </span>
        </div>
        <div class="dp-foot">
          <span class="dp-clear" @click="clearDate">清除日期</span>
        </div>
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
/* 触发输入框（只读展示，点击唤起弹层，隐藏原生控件图标） */
.dp-input {
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  font-size: 13px;
  color: var(--grey-80);
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  width: 124px;
  padding: 2px 4px;
  transition: all 0.2s var(--ease-spring);
}
.dp-input:hover {
  background: rgba(255, 255, 255, 0.72);
}
.dp-input::-webkit-calendar-picker-indicator {
  display: none;
}

/* 弹层 */
.dp-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1390;
}
.dp-pop {
  position: fixed;
  z-index: 1400;
  width: 252px;
  padding: 10px 12px 8px;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float);
  animation: dp-in 0.2s var(--ease-spring);
  user-select: none;
}
@keyframes dp-in {
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
.dp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.dp-title {
  font-size: 14px;
  color: var(--front-color);
}
.dp-btns {
  display: flex;
  gap: 4px;
}
.dp-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 22px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--grey-60);
}
.dp-btn:hover {
  background: var(--grey-5);
  color: var(--front-color);
}
.dp-today-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid currentColor;
  display: block;
}
.dp-week {
  display: flex;
  font-size: 11px;
}
.dp-w {
  flex: 1;
  text-align: center;
  line-height: 26px;
  color: var(--grey-40);
}
.dp-w.dim {
  color: var(--grey-30);
}
.dp-grid {
  display: flex;
  flex-wrap: wrap;
}
.dp-cell {
  width: calc(100% / 7);
  height: 38px;
}
.dp-day {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 32px;
  height: 38px;
  margin: 0 auto;
  font-size: 12px;
  border-radius: 8px;
  cursor: pointer;
}
.dp-day:hover {
  background: var(--grey-5);
}
.dp-num {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 22px;
  margin-top: 2px;
  border-radius: 999px;
  line-height: 22px;
}
.dp-day.out .dp-num {
  opacity: 0.4;
}
.dp-day.today .dp-num {
  color: var(--primary-color);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--primary-color);
}
.dp-day.sel .dp-num {
  background: var(--primary-color);
  color: #fff;
}
.dp-lunar {
  display: block;
  font-style: normal;
  font-size: 9px;
  line-height: 12px;
  color: var(--grey-40);
  max-width: 30px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dp-day.sel .dp-lunar {
  color: var(--grey-60);
}
.dp-flag {
  position: absolute;
  right: -3px;
  top: -2px;
  width: 12px;
  height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--green);
  background: rgba(255, 255, 255, 0.85);
  border-radius: 50%;
}
.dp-day.sel .dp-flag {
  color: #fff;
  background: var(--primary-color);
}
.dp-flag.work {
  color: var(--grey-40);
  font-size: 9px;
  line-height: 12px;
}
.dp-foot {
  display: flex;
  justify-content: center;
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px solid var(--grey-5);
}
.dp-clear {
  font-size: 12px;
  color: var(--grey-40);
  cursor: pointer;
  padding: 2px 12px;
  border-radius: 999px;
}
.dp-clear:hover {
  color: var(--warn-red);
  background: var(--grey-5);
}
</style>
