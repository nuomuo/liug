import { createApp } from 'vue';
import App from './App.vue';
import './styles/global.css';
import spriteUrl from './assets/icons.svg?url';

// 桌面四象限小组件模式（pywebview 无边框透明窗口加载 /quadrant）：body 背景透明
if (window.location.pathname.startsWith('/quadrant')) {
  document.body.classList.add('widget-mode');
}

// 注入与原版一致的 SVG 雪碧图（<use xlink:href="#icon-id"> 直接可用）
fetch(spriteUrl)
  .then((r) => r.text())
  .then((svg) => {
    const holder = document.createElement('div');
    holder.innerHTML = svg;
    holder.firstChild.style.position = 'absolute';
    holder.firstChild.style.width = '0';
    holder.firstChild.style.height = '0';
    document.body.insertBefore(holder.firstChild, document.body.firstChild);
  });

createApp(App).mount('#root');
