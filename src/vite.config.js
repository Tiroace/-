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
  // DeepSeek 密钥：只从环境变量注入，绝不写进代码/仓库（仓库是公开的）
  const deepseekKey = String(process.env.VITE_DEEPSEEK_KEY || '').trim();
  // 引擎开关（双版本令第三节）：一套代码出两个包。
  //   不设 / 其它值 → rules（规则版，默认，提审用这一版）
  //   deepseek     → DeepSeek 识图版（只能内部测试，不得提审）
  const engine = String(process.env.VITE_ENGINE || '').trim() === 'deepseek' ? 'deepseek' : 'rules';
  // 规则版红线：构建时看到密钥就直接报错退出，不指望「反正用不到」
  if (engine === 'rules' && deepseekKey) {
    throw new Error(
      '规则版构建时不允许存在 VITE_DEEPSEEK_KEY（当前有值）。' +
        '规则版不得包含任何密钥：先清掉该环境变量再构建。'
    );
  }
  return {
    plugins: [uni({ pagesJsonPath: resolvePagesJson() })],
    // 规则版把 judge.js 换成本地空实现：包体里不留提示词、接口地址和模型名。
    // 只换这一个文件，业务代码不用改；DeepSeek 版照旧用真文件。
    // 注意：这条 alias 只对 .js 有效；.vue 组件不走 vite alias（uni 先解析组件），
    // 上传卡的排除改为构建后清理，见 scripts/check-rules-build.mjs 与 build-engine.mjs。
    resolve: {
      alias:
        engine === 'rules'
          ? [{ find: /^@\/services\/judge\.js$/, replacement: path.join(HERE, 'src', 'services', 'judge.stub.js') }]
          : [],
    },
    define: {
      __QBL_API_BASE_URL__: JSON.stringify(apiBase),
      __QBL_CLOUD_ENV__: JSON.stringify(cloudEnv),
      __QBL_CLOUD_SERVICE__: JSON.stringify(cloudService),
      __QBL_DEEPSEEK_KEY__: JSON.stringify(deepseekKey),
      __QBL_ENGINE__: JSON.stringify(engine),
    },
    server: {
      host: '0.0.0.0',
    },
  };
});
