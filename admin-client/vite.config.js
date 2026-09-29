import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // 生产环境挂在后端 /system-admin/ 子路径下，资源引用必须带此前缀
  base: '/system-admin/',
  server: {
    port: 5181,
    proxy: {
      '/system': 'http://localhost:4300',
    },
  },
});
