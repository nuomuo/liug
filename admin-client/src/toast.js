/* 轻量 toast 状态（AppToast.vue 渲染，Teleport 到 body） */
import { reactive } from 'vue';

export const toast = reactive({ msg: '', error: false, show: false });

let timer = null;

export function showToast(msg, error = false) {
  toast.msg = msg;
  toast.error = error;
  toast.show = true;
  clearTimeout(timer);
  timer = setTimeout(() => {
    toast.show = false;
  }, 2600);
}
