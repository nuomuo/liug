<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { marked } from 'marked';
import Icon from './Icon.vue';

marked.setOptions({ gfm: true, breaks: true });

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '支持 Markdown，选中文本右键可快捷格式化' },
});
const emit = defineEmits(['update:modelValue']);

const contentEl = ref(null);
const livePreview = ref(true);
const ctxMenu = ref(null);
// 本地同步镜像：输入即时渲染预览，不等保存回包
const contentMirror = ref(props.modelValue);
watch(
  () => props.modelValue,
  (v) => {
    if ((v || '') !== contentMirror.value) contentMirror.value = v || '';
  }
);
const renderedHtml = computed(() => marked.parse(contentMirror.value || ''));

function onInput(e) {
  contentMirror.value = e.target.value;
  emit('update:modelValue', e.target.value);
}

// ---------- 左右分栏实时预览，分割条可拖动调节宽度占比 ----------
const rowSplit = computed(() => livePreview.value && !!contentMirror.value);
const splitRowEl = ref(null);
const editorRatio = ref(0.5); // 编辑区宽度占比（0.2 ~ 0.8）
let splitting = false;
function beginSplit(e) {
  if (e.button !== 0) return;
  splitting = true;
  document.body.style.userSelect = 'none';
  e.preventDefault();
  document.addEventListener('mousemove', onSplitMove);
  document.addEventListener('mouseup', endSplit);
}
function onSplitMove(e) {
  if (!splitting || !splitRowEl.value) return;
  const r = splitRowEl.value.getBoundingClientRect();
  editorRatio.value = Math.min(0.8, Math.max(0.2, (e.clientX - r.left) / r.width));
}
function endSplit() {
  splitting = false;
  document.body.style.userSelect = '';
  document.removeEventListener('mousemove', onSplitMove);
  document.removeEventListener('mouseup', endSplit);
}
onBeforeUnmount(endSplit);

// ---------- 右键格式化菜单 ----------
function openMenu(e) {
  ctxMenu.value = { x: e.clientX, y: e.clientY };
}
function closeMenu() {
  ctxMenu.value = null;
}
const ctxStyle = computed(() => {
  const m = ctxMenu.value;
  if (!m) return {};
  return {
    left: Math.max(8, Math.min(m.x, window.innerWidth - 180)) + 'px',
    top: Math.max(8, Math.min(m.y, window.innerHeight - 460)) + 'px',
  };
});

// 选区包裹式格式化（无选区时插入占位文本）
function wrapSel(before, after = before, placeholder = '文本') {
  closeMenu();
  const el = contentEl.value;
  const s = el.selectionStart;
  const e = el.selectionEnd;
  const v = el.value;
  const inner = v.slice(s, e) || placeholder;
  const nv = v.slice(0, s) + before + inner + after + v.slice(e);
  el.value = nv;
  contentMirror.value = nv;
  el.focus();
  el.setSelectionRange(s + before.length, s + before.length + inner.length);
  emit('update:modelValue', nv);
}
// 行前缀式格式化（再次应用会替换掉已有前缀）
function prefixLine(prefix) {
  closeMenu();
  const el = contentEl.value;
  const v = el.value;
  const s = el.selectionStart;
  const e = el.selectionEnd;
  const ls = v.lastIndexOf('\n', s - 1) + 1;
  let le = v.indexOf('\n', e);
  if (le === -1) le = v.length;
  const body = v.slice(ls, le).replace(/^(#{1,6}\s+|>\s?|[-*]\s+|\d+\.\s+)/, '');
  const nv = v.slice(0, ls) + prefix + body + v.slice(le);
  el.value = nv;
  contentMirror.value = nv;
  el.focus();
  el.setSelectionRange(ls + prefix.length + body.length, ls + prefix.length + body.length);
  emit('update:modelValue', nv);
}

const ctxItems = [
  { label: '加粗', hint: '**', run: () => wrapSel('**') },
  { label: '斜体', hint: '*', run: () => wrapSel('*') },
  { label: '下划线', hint: '<u>', run: () => wrapSel('<u>', '</u>') },
  { label: '删除线', hint: '~~', run: () => wrapSel('~~') },
  { label: '高亮', hint: '<mark>', run: () => wrapSel('<mark>', '</mark>', '重点') },
  { label: '红色', dot: '#e13e39', run: () => wrapSel('<span style="color:#e13e39">', '</span>') },
  { label: '橙色', dot: '#faa80c', run: () => wrapSel('<span style="color:#faa80c">', '</span>') },
  { label: '蓝色', dot: '#4772fa', run: () => wrapSel('<span style="color:#4772fa">', '</span>', '文字') },
  { label: '代码', hint: '`', run: () => wrapSel('`') },
  { label: '链接', hint: '[]()', run: () => wrapSel('[', '](https://)', '链接文字') },
  { sep: true },
  { label: '标题', hint: '##', run: () => prefixLine('## ') },
  { label: '无序列表', hint: '-', run: () => prefixLine('- ') },
  { label: '有序列表', hint: '1.', run: () => prefixLine('1. ') },
  { label: '引用', hint: '>', run: () => prefixLine('> ') },
];
</script>

<template>
  <div class="md-editor">
    <div class="md-bar">
      <span class="md-switch" :class="{ on: livePreview }" @click="livePreview = !livePreview">实时预览</span>
    </div>
    <div ref="splitRowEl" class="md-row" :class="{ split: rowSplit }">
      <textarea
        ref="contentEl"
        class="md-input"
        :class="{ compact: livePreview && !rowSplit }"
        :style="rowSplit ? { width: `calc(${editorRatio * 100}% - 5px)` } : null"
        :value="contentMirror"
        :placeholder="placeholder"
        @input="onInput"
        @contextmenu.prevent="openMenu"
      ></textarea>
      <template v-if="rowSplit">
        <div class="md-splitter" title="拖动调节宽度" @mousedown="beginSplit"></div>
        <div class="md-preview" v-html="renderedHtml"></div>
      </template>
    </div>

    <!-- 右键格式化菜单（Teleport 出容器，避免被裁剪/受层叠上下文影响） -->
    <Teleport to="body">
      <template v-if="ctxMenu">
        <div class="ctx-backdrop" @mousedown="closeMenu" @contextmenu.prevent="closeMenu"></div>
        <div class="ctx-menu" :style="ctxStyle" @contextmenu.prevent>
          <template v-for="(it, i) in ctxItems" :key="i">
            <div v-if="it.sep" class="ctx-sep"></div>
            <div v-else class="ctx-item" @mousedown.prevent="it.run()">
              <span v-if="it.dot" class="ctx-dot" :style="{ background: it.dot }"></span>
              <span class="ctx-label">{{ it.label }}</span>
              <span v-if="it.hint" class="ctx-hint">{{ it.hint }}</span>
            </div>
          </template>
        </div>
      </template>
    </Teleport>
  </div>
</template>

<style scoped>
.md-editor {
  width: 100%;
}
.md-input {
  width: 100%;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  font-size: 13px;
  line-height: 20px;
  min-height: 70px;
  padding: 6px;
  color: var(--grey-80);
  resize: vertical;
  background: transparent;
  transition: all 0.2s var(--ease-spring);
}
.md-input:hover,
.md-input:focus {
  background: rgba(255, 255, 255, 0.55);
}
.md-input:focus {
  border-color: var(--primary-color);
}
/* 预览开关 */
.md-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 2px;
}
.md-switch {
  font-size: 12px;
  color: var(--grey-40);
  cursor: pointer;
  padding: 2px 10px;
  border-radius: 999px;
  transition: all 0.2s var(--ease-spring);
}
.md-switch:hover {
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.5);
}
.md-switch.on {
  color: var(--primary-color);
  background: rgba(255, 255, 255, 0.55);
}
/* 实时预览开启但无内容时压缩编辑区 */
.md-input.compact {
  min-height: 48px;
}
/* 左右分栏：编辑区 | 分割条 | 预览区 */
.md-row.split {
  display: flex;
  align-items: stretch;
}
.md-row.split .md-input {
  flex: none;
  height: 170px;
  min-height: 170px;
}
.md-row.split .md-preview {
  flex: 1;
  min-width: 0;
  min-height: 170px;
  max-height: none;
}
.md-splitter {
  flex: none;
  width: 3px;
  margin: 0 1px;
  border-radius: 2px;
  cursor: col-resize;
  background: var(--grey-20);
  transition: background 0.15s var(--ease-spring);
}
.md-splitter:hover {
  background: color-mix(in srgb, var(--primary-color) 25%, transparent);
}
/* 渲染预览排版 */
.md-preview {
  min-height: 40px;
  max-height: 320px;
  overflow-y: auto;
  padding: 8px 10px;
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.35);
  font-size: 13px;
  line-height: 20px;
  color: var(--grey-80);
  word-break: break-word;
}
.md-preview :deep(p) { margin: 0 0 6px; }
.md-preview :deep(p:last-child) { margin-bottom: 0; }
.md-preview :deep(h1),
.md-preview :deep(h2),
.md-preview :deep(h3),
.md-preview :deep(h4) { margin: 8px 0 4px; line-height: 1.35; }
.md-preview :deep(h1) { font-size: 17px; }
.md-preview :deep(h2) { font-size: 16px; }
.md-preview :deep(h3) { font-size: 14.5px; }
.md-preview :deep(h4) { font-size: 13.5px; }
.md-preview :deep(ul),
.md-preview :deep(ol) { margin: 0 0 6px; padding-left: 20px; }
.md-preview :deep(li) { margin: 2px 0; }
.md-preview :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 12px;
}
.md-preview :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  padding: 8px 10px;
  overflow-x: auto;
  margin: 0 0 6px;
}
.md-preview :deep(pre code) { background: none; padding: 0; }
.md-preview :deep(blockquote) {
  margin: 0 0 6px;
  padding: 2px 10px;
  border-left: 3px solid var(--grey-20);
  color: var(--grey-60);
}
.md-preview :deep(mark) { background: #ffe58a; border-radius: 2px; padding: 0 2px; }
.md-preview :deep(a) { color: var(--primary-color); }
.md-preview :deep(del) { color: var(--grey-40); }
.md-preview :deep(hr) { border: none; border-top: 1px solid var(--grey-13); margin: 8px 0; }

/* 右键格式化菜单 */
.ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1490;
}
.ctx-menu {
  position: fixed;
  z-index: 1500;
  min-width: 160px;
  padding: 5px 0;
  background: var(--glass-heavy-bg);
  -webkit-backdrop-filter: var(--glass-heavy-blur);
  backdrop-filter: var(--glass-heavy-blur);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--glass-shadow-float);
  animation: md-pop-in 0.18s var(--ease-spring);
}
@keyframes md-pop-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); filter: blur(4px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}
.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 14px;
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
  transition: background 0.15s var(--ease-spring);
}
.ctx-item:hover { background: var(--grey-5); }
.ctx-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex: none;
}
.ctx-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--grey-30);
}
.ctx-sep {
  height: 1px;
  background: var(--grey-5);
  margin: 4px 8px;
}
</style>
