<script setup>
import { computed, ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { store, showToast, placeDropdown } from '../store.js';
import { api } from '../api.js';
import { computeCountdown } from '../lib/countdown.js';
import Icon from './Icon.vue';

const TYPE_META = {
  anniversary: { label: '纪念日', img: '/cd_anniversary.jpg' },
  countdown: { label: '倒数日', img: '/cd_preset_countdown.jpg' },
  birthday: { label: '生日', img: '/cd_birthday.jpg' },
  festival: { label: '节日', img: null, gradient: 'linear-gradient(135deg, #c0392b 0%, #e67e22 60%, #f1c40f 130%)' },
};
const FILTERS = [
  { key: 'all', label: '所有' },
  { key: 'anniversary', label: '纪念日' },
  { key: 'countdown', label: '倒数日' },
  { key: 'birthday', label: '生日' },
  { key: 'festival', label: '节日' },
];

const activeFilter = ref('all');
const list = computed(() => {
  const src = [...store.countdowns].sort((a, b) => (b.pinned - a.pinned) || (a.sortOrder - b.sortOrder));
  if (activeFilter.value === 'all') return src;
  return src.filter((c) => c.type === activeFilter.value);
});

// ---------- 卡片展示计算 ----------
function cardInfo(cd) {
  const r = computeCountdown(cd);
  let numbers = [];
  let desc;
  if (cd.type === 'anniversary') {
    const parts = [];
    if (r.years > 0) parts.push({ n: r.years, u: '年' });
    if (r.months > 0 || r.years > 0) parts.push({ n: r.months, u: '月' });
    parts.push({ n: r.days, u: '天' });
    numbers = parts;
    const [y, m, d] = cd.date.split('-');
    desc = `距离 ${y}年${m}月${d}日 已经`;
  } else if (cd.type === 'countdown' && !cd.repeatYearly) {
    numbers = [{ n: r.days, u: '天' }];
    const [y, m, d] = cd.date.split('-');
    desc = r.dir === 'future' ? `距离 ${y}年${m}月${d}日 还有` : `距离 ${y}年${m}月${d}日 已经`;
  } else {
    numbers = [{ n: r.days, u: '天' }];
    const lbl = cd.isLunar ? `农历${cd.date.slice(5).replace('-', '月')}日` : cd.date.slice(5).replace('-', '月') + '日';
    desc = r.days === 0 ? `今天就是${cd.title}` : `距离 ${lbl} 还有`;
  }
  if (r.days === 0 && cd.type !== 'anniversary') numbers = [{ n: 0, u: '天' }];
  return { ...r, numbers, desc };
}

// ---------- 编辑弹窗 ----------
const editOpen = ref(false);
const form = reactive({ id: null, title: '', type: 'countdown', date: '', isLunar: false, repeatYearly: true, pinned: false });

const todayStr = new Date().toISOString().slice(0, 10);

function openAdd(type = 'countdown') {
  Object.assign(form, {
    id: null, title: '', type, date: todayStr, isLunar: false, repeatYearly: type !== 'countdown', pinned: false,
  });
  editOpen.value = true;
}
function openEdit(cd) {
  Object.assign(form, {
    id: cd.id, title: cd.title, type: cd.type, date: cd.date, isLunar: cd.isLunar, repeatYearly: cd.repeatYearly, pinned: cd.pinned,
  });
  editOpen.value = true;
}
async function save() {
  if (!form.title.trim()) {
    showToast('请输入标题');
    return;
  }
  const payload = { ...form, title: form.title.trim() };
  try {
    if (form.id) {
      const updated = await api.updateCountdown(form.id, payload);
      const i = store.countdowns.findIndex((c) => c.id === form.id);
      if (i >= 0) store.countdowns[i] = updated;
    } else {
      store.countdowns.push(await api.createCountdown(payload));
    }
    editOpen.value = false;
    showToast('已保存');
  } catch (e) {
    showToast('保存失败：' + (e.data?.error || e.message));
  }
}
async function remove(cd) {
  if (confirm(`确定删除「${cd.title}」吗？`)) {
    await api.deleteCountdown(cd.id);
    store.countdowns = store.countdowns.filter((c) => c.id !== cd.id);
  }
}
async function togglePin(cd) {
  const updated = await api.updateCountdown(cd.id, { pinned: !cd.pinned });
  Object.assign(cd, updated);
  store.countdowns = [...store.countdowns];
}

// 每卡片 hover 菜单（在触发位置弹出）
const menuFor = ref(null);
const menuTriggerEl = ref(null);
const menuElRef = ref(null);
async function toggleCardMenu(cd, e) {
  menuFor.value = menuFor.value === cd.id ? null : cd.id;
  if (menuFor.value) {
    menuTriggerEl.value = e.currentTarget;
    await nextTick();
    placeDropdown(menuElRef.value, menuTriggerEl.value, { align: 'right' });
  }
}
function onDocClick(e) {
  if (!e.target.closest('.cd-more')) menuFor.value = null;
}
onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));
</script>

<template>
  <div class="cd-page">
    <header class="tl-bar">
      <div class="tl-left">
        <h5 class="tl-des">倒数纪念日</h5>
      </div>
      <div class="tl-right">
        <span class="tl-icon" title="添加" @click="openAdd('countdown')"><Icon name="add" :size="20" /></span>
        <span class="tl-icon tl-more" title="更多" @click="openAdd('festival')"><Icon name="more-titlebar" :size="20" /></span>
      </div>
    </header>

    <div class="cd-filters">
      <div
        v-for="f in FILTERS"
        :key="f.key"
        class="filter-pill"
        :class="{ active: activeFilter === f.key }"
        @click="activeFilter = f.key"
      >
        {{ f.label }}
      </div>
    </div>

    <div class="cd-scroll">
      <div class="cd-grid">
        <div v-for="cd in list" :key="cd.id" class="cd-card group">
          <div class="cd-bg" :style="TYPE_META[cd.type].gradient ? { background: TYPE_META[cd.type].gradient } : { backgroundImage: `url(${TYPE_META[cd.type].img})`, backgroundSize: 'cover', backgroundPosition: 'center top' }"></div>
          <div class="cd-overlay"></div>

          <div class="cd-content">
            <div class="cd-title-row">
              <span class="cd-title">{{ cd.title }}</span>
              <span v-if="cd.pinned" class="cd-pinned-mark"><Icon name="countdown-pinned" :size="14" /></span>
            </div>
            <div class="cd-numbers">
              <template v-for="(p, i) in cardInfo(cd).numbers" :key="i">
                <span class="cd-number">{{ p.n }}</span>
                <span class="cd-unit">{{ p.u }}</span>
              </template>
            </div>
            <div class="cd-desc">{{ cardInfo(cd).desc }}</div>
          </div>

          <div class="cd-actions">
            <span class="cd-act" :title="cd.pinned ? '取消置顶' : '置顶'" @click.stop="togglePin(cd)">
              <Icon :name="cd.pinned ? 'countdown-pinned' : 'countdown-unpinned'" :size="18" />
            </span>
            <span class="cd-act cd-more" title="更多" @click.stop="toggleCardMenu(cd, $event)">
              <Icon name="more-titlebar" :size="18" />
              <div v-if="menuFor === cd.id" ref="menuElRef" class="dropdown-menu cd-menu" @click.stop>
                <li @click="openEdit(cd); menuFor = null">编辑</li>
                <li @click="togglePin(cd); menuFor = null">{{ cd.pinned ? '取消置顶' : '置顶' }}</li>
                <li class="danger" @click="remove(cd); menuFor = null">删除</li>
              </div>
            </span>
          </div>
        </div>

        <div class="cd-card cd-add-card" @click="openAdd('countdown')">
          <div class="cd-add-inner">
            <Icon name="add" :size="28" />
            <span>添加</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="editOpen" class="cd-modal-backdrop" @mousedown.self="editOpen = false">
      <div class="cd-modal" @mousedown.stop>
        <div class="cd-modal-title">{{ form.id ? '编辑' : '添加' }}{{ TYPE_META[form.type].label }}</div>

        <input v-model="form.title" class="cd-input title" placeholder="名称，如：恋爱纪念日" @keydown.enter="save" />

        <div class="cd-form-row">
          <span class="cd-form-label">类型</span>
          <div class="type-pills">
            <span
              v-for="(meta, key) in TYPE_META"
              :key="key"
              class="type-pill"
              :class="{ active: form.type === key }"
              @click="form.type = key"
            >
              {{ meta.label }}
            </span>
          </div>
        </div>

        <div class="cd-form-row">
          <span class="cd-form-label">日期</span>
          <input v-model="form.date" type="date" class="cd-input date" />
          <label class="lunar-toggle">
            <input v-model="form.isLunar" type="checkbox" />
            农历
          </label>
        </div>
        <div v-if="form.isLunar" class="lunar-hint">农历模式：所选日期的「月-日」按农历解释（春节 = 农历1月1日）</div>

        <div class="cd-form-row checks">
          <label>
            <input v-model="form.repeatYearly" type="checkbox" />
            每年重复
          </label>
          <label>
            <input v-model="form.pinned" type="checkbox" />
            置顶
          </label>
        </div>

        <div class="cd-modal-actions">
          <button class="cd-cancel" @click="editOpen = false">取消</button>
          <button class="cd-save" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cd-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 6px 6px 6px 0;
  background: var(--main-background-color);
  border-radius: 10px;
  min-width: 0;
}
.tl-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 20px 10px;
  flex: none;
}
.tl-des {
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
}
.tl-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.tl-icon {
  display: inline-flex;
  padding: 4px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--grey-60);
}
.tl-icon:hover {
  background: var(--grey-5);
  color: var(--front-color);
}

.cd-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 0 20px 10px;
  flex: none;
}
.filter-pill {
  padding: 5px 12px;
  line-height: 20px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
  color: var(--grey-60);
  transition: all 0.12s;
}
.filter-pill:hover {
  background: var(--grey-4);
}
.filter-pill.active {
  background: var(--primary-color);
  color: #fff;
}

.cd-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px 20px 20px;
}
.cd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 20px;
}
.cd-card {
  position: relative;
  height: 173px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 0 6.06px rgba(25, 25, 25, 0.03);
  cursor: default;
}
.cd-bg {
  position: absolute;
  inset: 0;
}
.cd-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
}
.cd-content {
  position: relative;
  z-index: 10;
  height: 100%;
  display: flex;
  flex-direction: column;
  color: #fff;
}
.cd-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 26px;
  padding: 0 24px;
}
.cd-title {
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cd-pinned-mark {
  display: inline-flex;
  color: rgba(255, 255, 255, 0.9);
  flex: none;
}
.cd-numbers {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px 0 0;
}
.cd-number {
  font-size: 42px;
  line-height: 58px;
  font-weight: 600;
  color: #fff;
}
.cd-unit {
  font-size: 18px;
  line-height: 38px;
  margin-left: 4px;
  color: #fff;
}
.cd-desc {
  height: 17px;
  font-size: 11px;
  line-height: 17px;
  text-align: center;
  color: rgba(255, 255, 255, 0.85);
  padding: 0 24px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-bottom: 8px;
}

.cd-actions {
  position: absolute;
  z-index: 20;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 8px;
  visibility: hidden;
}
.cd-card:hover .cd-actions {
  visibility: visible;
}
.cd-act {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 5px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.9);
}
.cd-act:hover {
  background: rgba(255, 255, 255, 0.2);
}
.cd-menu {
  min-width: 110px;
}

.cd-add-card {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--grey-20);
  background: var(--card-bg);
  cursor: pointer;
  box-shadow: none;
}
.cd-add-card:hover {
  border-color: var(--primary-color);
}
.cd-add-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--grey-40);
  font-size: 13px;
}
.cd-add-card:hover .cd-add-inner {
  color: var(--primary-color);
}

/* 弹窗 */
.cd-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1500;
  background: rgba(0, 0, 0, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cd-modal {
  width: 380px;
  max-width: 92vw;
  background: #fff;
  border-radius: 12px;
  box-shadow: var(--default-shadow);
  padding: 18px 20px;
  animation: pop-in 0.15s ease-out;
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: none; }
}
.cd-modal-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
}
.cd-input {
  width: 100%;
  height: 34px;
  border: 1px solid var(--grey-20);
  border-radius: 7px;
  padding: 0 10px;
  font-size: 14px;
  color: var(--front-color);
}
.cd-input.title {
  font-size: 15px;
  margin-bottom: 14px;
}
.cd-form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.cd-form-label {
  font-size: 13px;
  color: var(--grey-60);
  width: 36px;
  flex: none;
}
.type-pills {
  display: flex;
  gap: 6px;
}
.type-pill {
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 12px;
  cursor: pointer;
  background: var(--grey-5);
  color: var(--grey-80);
}
.type-pill:hover {
  background: var(--grey-10);
}
.type-pill.active {
  background: var(--primary-color);
  color: #fff;
}
.cd-input.date {
  flex: 1;
  min-width: 0;
}
.lunar-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--grey-80);
  cursor: pointer;
  flex: none;
}
.cd-form-row.checks {
  gap: 20px;
}
.lunar-hint {
  font-size: 11px;
  color: var(--grey-40);
  margin: -6px 0 12px 46px;
}
.cd-form-row.checks label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--grey-80);
  cursor: pointer;
}
.cd-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
.cd-cancel {
  height: 32px;
  padding: 0 18px;
  border: 1px solid var(--grey-20);
  border-radius: 7px;
  font-size: 13px;
  color: var(--grey-80);
}
.cd-cancel:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}
.cd-save {
  height: 32px;
  padding: 0 22px;
  border-radius: 7px;
  background: var(--primary-color);
  color: #fff;
  font-size: 13px;
}
.cd-save:hover {
  background: var(--primary-hover-color);
}
</style>
