// 构建配置：uni-app Vue3 + Vite
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import uni from '@dcloudio/vite-plugin-uni';

const HERE = path.dirname(fileURLToPath(import.meta.url));

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

// 小程序页面/窗口配置（pages.json）按构建目标区分，两套配置各自独立、互不覆盖：
//   - 开发构建（uni -p mp-weixin / npm run dev:*）：src/pages.json，tabBar 三项（含广场），供后续开放联调
//   - 提审构建（npm run build:review:*，内部设 QBL_BUILD_TARGET=review）：src/pages.review.json，
//     tabBar 只保留「检查」「我的」，广场页不进 tabBar（BUG-20261103-02；页面文件保留、代码不删）
function resolvePagesJson() {
  const target = String(process.env.QBL_BUILD_TARGET || '').trim().toLowerCase();
  if (target === 'review') {
    const review = path.join(HERE, 'src', 'pages.review.json');
    if (!fs.existsSync(review)) {
      throw new Error('提审构建找不到 ' + review);
    }
    return review;
  }
  return path.join(HERE, 'src', 'pages.json');
}

export default defineConfig(({ command, mode }) => {
  const apiBase = resolveApiBase(command, mode);
  // 微信云托管（D38）：环境 ID 与服务名由构建时注入，不写死在源码里。
  //   $env:VITE_CLOUD_ENV="prod-xxx"; $env:VITE_CLOUD_SERVICE="qbl-api"; npm run build:mp-weixin
  const cloudEnv = String(process.env.VITE_CLOUD_ENV || '').trim();
  const cloudService = String(process.env.VITE_CLOUD_SERVICE || '').trim();
  return {
    plugins: [uni({ pagesJsonPath: resolvePagesJson() })],
    define: {
      __QBL_API_BASE_URL__: JSON.stringify(apiBase),
      __QBL_CLOUD_ENV__: JSON.stringify(cloudEnv),
      __QBL_CLOUD_SERVICE__: JSON.stringify(cloudService),
    },
    server: {
      host: '0.0.0.0',
    },
  };
});
