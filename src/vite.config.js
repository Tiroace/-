// 构建配置：uni-app Vue3 + Vite
import { defineConfig } from 'vite';
import uni from '@dcloudio/vite-plugin-uni';

// 真后端地址不写死在源码里，由构建时注入：
//   - 开发构建（uni -p mp-weixin）默认注入本机后端地址，方便联调
//   - 生产构建（uni build -p mp-weixin）默认注入空串，产物里不会出现内网地址
// 需要改地址时设环境变量：$env:VITE_API_BASE_URL = "http://x.x.x.x:8000"
function resolveApiBase(command, mode) {
  const fromEnv = process.env.VITE_API_BASE_URL;
  if (fromEnv !== undefined && fromEnv !== '') return fromEnv;
  // command: 'serve' 是开发构建，'build' 是生产构建
  if (command === 'serve' || mode === 'development') return 'http://127.0.0.1:8000';
  return '';
}

export default defineConfig(({ command, mode }) => {
  const apiBase = resolveApiBase(command, mode);
  return {
    plugins: [uni()],
    define: {
      __QBL_API_BASE_URL__: JSON.stringify(apiBase),
    },
    server: {
      host: '0.0.0.0',
    },
  };
});
