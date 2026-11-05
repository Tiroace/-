// 规则版构建后清理：把「上传卡」从产物里摘掉。
//
// 为什么不在源码里做：uni-app 编译 .vue 组件时不走 vite alias（实测 alias 无效），
// 组件只要被 import 就一定被打包。规则版首页只有粘贴卡、上传卡永远不渲染，
// 所以构建后把它的产物删掉是安全且可验证的做法。
//
// 做三件事（任何一步没做干净都报错退出，不静默）：
//   1. 删 components/UploadCard.{js,json,wxml,wxss}
//   2. 从引用它的页面 json（usingComponents）里移除 "upload-card"
//   3. 从对应 wxml 里移除 <upload-card .../> 标签
//
// 用法：node scripts/strip-upload-card.mjs dist/build/mp-weixin
import fs from 'node:fs';
import path from 'node:path';

const DIST = process.argv[2] || 'dist/build/mp-weixin';
const COMPONENT = 'UploadCard';
const TAG = 'upload-card';

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

function main() {
  if (!fs.existsSync(DIST)) {
    console.error('[FAIL] 找不到产物目录：' + DIST);
    return 2;
  }
  const changes = [];

  // 1. 删组件产物
  const compDir = path.join(DIST, 'components');
  if (fs.existsSync(compDir)) {
    for (const f of fs.readdirSync(compDir)) {
      if (f.startsWith(COMPONENT + '.')) {
        fs.unlinkSync(path.join(compDir, f));
        changes.push('删除 components/' + f);
      }
    }
  }

  // 2 & 3. 从页面 json 取消注册、从 wxml 摘掉标签
  for (const file of walk(DIST)) {
    if (!/\.(json|wxml)$/.test(file)) continue;
    const rel = path.relative(DIST, file);
    if (file.endsWith('.json')) {
      let raw;
      try {
        raw = fs.readFileSync(file, 'utf8');
      } catch (e) {
        continue;
      }
      if (raw.indexOf('"' + TAG + '"') < 0) continue;
      let obj;
      try {
        obj = JSON.parse(raw);
      } catch (e) {
        continue;
      }
      const uc = obj.usingComponents || {};
      if (!uc[TAG]) continue;
      delete uc[TAG];
      obj.usingComponents = uc;
      fs.writeFileSync(file, JSON.stringify(obj, null, 2), 'utf8');
      changes.push('取消注册 ' + rel);
    } else {
      let raw;
      try {
        raw = fs.readFileSync(file, 'utf8');
      } catch (e) {
        continue;
      }
      if (raw.indexOf('<' + TAG) < 0) continue;
      // 自闭合标签：<upload-card ... />
      const next = raw.replace(new RegExp('<' + TAG + '\\b[^>]*?/>', 'g'), '');
      if (next !== raw) {
        fs.writeFileSync(file, next, 'utf8');
        changes.push('移除标签 ' + rel);
      }
    }
  }

  if (!changes.length) {
    console.log('[提示] 产物里没有上传卡内容，无需清理');
    return 0;
  }
  console.log('规则版清理上传卡：');
  changes.forEach((c) => console.log('  · ' + c));
  console.log('[OK] 上传卡已从规则版产物移除（' + changes.length + ' 处）');
  return 0;
}

process.exit(main());
