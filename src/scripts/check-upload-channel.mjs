// 上传通道一致性断言（个人助理要求：产物里不能同时存在两套上传路径的开关混乱）
//
// 口径：
//   云托管已配置（CLOUD_ENV + CLOUD_SERVICE 都注入）→ 截图上传必须只走 base64 端点
//   未配置                                        → 走 multipart，且不得调用 base64 端点
// 两条通道并存是允许的（本地联调要用 multipart），但「选哪条」只能由 hasCloudBackend() 决定，
// 不允许出现第二个开关、也不允许在云托管模式下还走 uni.uploadFile。
//
// 用法：node scripts/check-upload-channel.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const REPO = path.resolve(ROOT, '..');
const SRC = path.join(ROOT, 'src');

const rows = [];
const ok = (n, d) => rows.push({ n, pass: true, d: d || '' });
const bad = (n, d) => rows.push({ n, pass: false, d: d || '' });
const read = (p) => fs.readFileSync(p, 'utf8');

try {
  const transport = read(path.join(SRC, 'services', 'transport.js'));
  const api = read(path.join(SRC, 'services', 'api.js'));
  const config = read(path.join(SRC, 'common', 'config.js'));

  // 1. 通道选择只有一个判据
  const branchCount = (transport.match(/hasCloudBackend\(\)/g) || []).length;
  branchCount >= 1 && branchCount <= 3
    ? ok('上传通道由 hasCloudBackend() 单点判定（出现 ' + branchCount + ' 次）')
    : bad('transport.js 里 hasCloudBackend() 出现 ' + branchCount + ' 次，疑似多处开关');

  // 2. 云托管分支必须走 base64 端点
  /if\s*\(\s*!hasCloudBackend\(\)\s*\)\s*\{[\s\S]*?httpUpload\(/.test(transport)
    ? ok('未配置云托管 → multipart 通道')
    : bad('未找到「未配置云托管走 multipart」的分支');
  /path:\s*base64Path/.test(transport)
    ? ok('云托管分支走 base64 端点')
    : bad('云托管分支没有走 base64 端点');

  // 3. api.js 传了两个端点，且没有绕过 transport 自己拼 uni.uploadFile
  /base64Path:\s*'\/analysis\/upload-base64'/.test(api)
    ? ok('api.js 声明 base64 端点 /analysis/upload-base64')
    : bad('api.js 没有声明 base64 端点');
  /uni\.uploadFile/.test(api)
    ? bad('api.js 仍然直接调用 uni.uploadFile（应统一走 transport）')
    : ok('api.js 不直接调用 uni.uploadFile');

  // 4. 不能有第二个上传开关
  const extraSwitch = /uploadMode|useBase64Upload|UPLOAD_MODE/i.test(transport + api + config);
  extraSwitch
    ? bad('发现第二个上传开关（uploadMode/useBase64Upload/UPLOAD_MODE）')
    : ok('没有第二个上传开关');

  // 5. 压缩参数符合约定
  const img = read(path.join(SRC, 'platform', 'image.js'));
  /MAX_EDGE\s*=\s*1080/.test(img) ? ok('压缩边长上限 1080') : bad('压缩边长不是 1080');
  /TARGET_BYTES\s*=\s*200\s*\*\s*1024/.test(img) ? ok('压缩目标 ≤200KB') : bad('压缩目标不是 200KB');

  // 6. 旧 multipart 端点保留（后端不删）
  const router = read(path.join(REPO, 'backend', 'app', 'routers', 'analysis.py'));
  /@router\.post\("\/analysis\/upload"\)/.test(router)
    ? ok('后端保留 multipart /analysis/upload')
    : bad('后端 multipart 端点被删了');
  /@router\.post\("\/analysis\/upload-base64"\)/.test(router)
    ? ok('后端已有 base64 /analysis/upload-base64')
    : bad('后端缺 base64 端点');
} catch (e) {
  bad('检查异常', e && e.message ? e.message : String(e));
}

let failed = 0;
console.log('');
for (const r of rows) {
  if (r.pass) console.log('  ✓ ' + r.n + (r.d ? '  -- ' + r.d : ''));
  else {
    failed += 1;
    console.log('  ✗ ' + r.n + (r.d ? '  -- ' + r.d : ''));
  }
}
console.log('');
if (failed) {
  console.log('✗ 上传通道检查失败（' + failed + '/' + rows.length + '）');
  process.exit(1);
}
console.log('✓ 上传通道检查全部通过（' + rows.length + ' 项）');
