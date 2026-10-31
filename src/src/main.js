import { createSSRApp } from 'vue';
import App from './App.vue';

// 小程序端的应用入口。使用 createSSRApp 以兼容 uni-app 双端运行。
export function createApp() {
  const app = createSSRApp(App);
  return { app };
}
