// 双版本构建入口（老板 2026-11-05 双版本令第三节）。
//
// 用法：
//   npm run build:rules           → 规则版（VITE_ENGINE=rules，默认值，提审用这一版）
//   npm run build:rules:review    → 规则版提审包（额外去掉广场 tab、开发自测页）
//   npm run build:deepseek        → DeepSeek 识图版（只能内部测试，不得提审）
//
// 为什么不用 cross-env：项目没装这个依赖，多一个包不值得；跨平台设置环境变量 Node 本身就够。
// 规则版不许带密钥：这里主动把 VITE_DEEPSEEK_KEY 清掉再交给 vite（vite.config.js 里还有一道硬报错）。
import { spawnSync } from 'node:child_process';

const engine = process.argv[2] === 'deepseek' ? 'deepseek' : 'rules';
// 提审包模式：第 3 个参数写 review，或环境变量 QBL_BUILD_TARGET=review
const IS_REVIEW =
  process.argv[3] === 'review' || String(process.env.QBL_BUILD_TARGET || '').trim().toLowerCase() === 'review';

const env = { ...process.env, VITE_ENGINE: engine };
if (IS_REVIEW) env.QBL_BUILD_TARGET = 'review';
if (engine === 'rules') {
  // 规则版红线：绝不能有密钥进产物
  delete env.VITE_DEEPSEEK_KEY;
} else if (!env.VITE_DEEPSEEK_KEY) {
  console.error('[FAIL] DeepSeek 版必须注入 VITE_DEEPSEEK_KEY（密钥只从环境变量来，不写代码）');
  process.exit(2);
}

console.log(
  '[engine] 构建引擎：' +
    engine +
    (engine === 'rules' ? '（规则版，提审用）' : '（DeepSeek 版，不得提审）') +
    (IS_REVIEW ? ' · 提审包模式' : '')
);

// 直接调 uni 的真实入口，不经过 npm / npm.cmd：
// npm.cmd 在 Windows 下 spawnSync 拿不到 stdio，出错时只会看到空白，排查成本很高。
const UNI_JS = 'node_modules/@dcloudio/vite-plugin-uni/bin/uni.js';
// 提审包要额外给 strip-dev-build / postbuild-check 传 review，否则广场 tab 会一起出去。
// 注意：非提审包也必须跑 strip-dev-build（不带 review），它负责删掉「开发自测」页等 dev 产物；
// 漏了这一步，开发者工具上传会报 ENOENT pages/dev/index.wxss（踩过一次）。
const extra = IS_REVIEW ? ['review'] : [];
// 规则版：清掉「上传卡」组件产物（规则版只有粘贴卡）。必须在 postbuild-check 之前跑，
// 让它能对清理后的产物做最后的词表核对。
const stripUpload =
  engine === 'rules'
    ? [[process.execPath, ['scripts/strip-upload-card.mjs', 'dist/build/mp-weixin']]]
    : [];
const steps = [
  [process.execPath, [UNI_JS, 'build', '-p', 'mp-weixin']],
  [process.execPath, ['scripts/strip-dev-build.mjs', 'dist/build/mp-weixin'].concat(extra)],
]
  .concat(stripUpload)
  .concat([[process.execPath, ['scripts/postbuild-check.mjs', 'dist/build/mp-weixin'].concat(extra)]]);
for (const [cmd, args] of steps) {
  // eslint-disable-next-line no-await-in-loop
  const r = spawnSync(cmd, args, { stdio: 'inherit', env, shell: false });
  if (r.error) {
    console.error('[FAIL] ' + cmd + ' 启动失败：' + r.error.message);
    process.exit(1);
  }
  if (r.status !== 0) {
    console.error('[FAIL] 步骤失败：' + args.join(' ') + '（退出码 ' + r.status + '）');
    process.exit(r.status || 1);
  }
}

// 规则版必须跑产物自检；失败就红，不许带着 deepseek 字样去提审
if (engine === 'rules') {
  const c = spawnSync(process.execPath, ['scripts/check-rules-build.mjs', 'dist/build/mp-weixin'], {
    stdio: 'inherit',
  });
  process.exit(c.status || 0);
}
