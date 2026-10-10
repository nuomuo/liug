import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  // 生产：由 server 在 /admin/ 路径托管，资源前缀必须一致；开发：跑在 / 下，/admin 走代理到后端
  base: command === 'build' ? '/admin/' : '/',
  server: {
    port: 5181,
    proxy: {
      '/admin': 'http://localhost:4300',
    },
  },
}));
