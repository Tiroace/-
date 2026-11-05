// 规则版构建后自检（双版本令第二节第 3 条）：
// 在规则版构建产物里搜四个词，结果必须全部为 0：
//   deepseek（不区分大小写）、api.deepseek.com、sk-、深度求索
//
// 另外再查一条（第二节第 2 条「不调服务器、不调云托管」）：
//   首页与「我的」页的产物里不得出现登录、上报、广告领奖这类会发请求的调用。
//   只查这两个页面：规则版里真正会跑的入口就它们，广场已经在提审包里摘掉。
//
// 为什么要有脚本：光靠「代码里没写」不算数，产物里可能来自依赖、注释、或者别名没生效。
// 每次出规则版都必须跑这个，结果贴给老板。
//
// 用法：node scripts/check-rules-build.mjs dist/build/mp-weixin
import fs from 'node:fs';
import path from 'node:path';

const DIST = process.argv[2] || 'dist/build/mp-weixin';
const WORDS = ['deepseek', 'api.deepseek.com', 'sk-', '深度求索'];
// 规则版页面里不该出现的联网调用（变量名会被压缩，所以查的是字符串字面量和方法名）
const NET_CALLS = ['ensureLogin', 'refreshUser', 'createAnalysis', 'fetchReports', 'claimAdReward', 'reportStats', 'callContainer'];
const NET_PAGES = ['pages/index/index.js', 'pages/mine/index.js'];
// 规则版界面上不得出现的截图类文案（双版本令第二节第 2 条：规则版界面不出现「上传截图」）。
// 规则版首页是粘贴卡；上传卡只属于识图版。这些词若出现在规则版包内，说明上传卡被带进去了。
const SCREENSHOT_WORDS = ['点这里选截图', '最多 3 张', '选截图，开始检查', '再加一张'];

// sk- 只算「像密钥」的：sk- 后面跟一长串字母数字。文档/普通文案里的 sk- 不算，但要单独列出来供人工确认。
const SECRET_LIKE = /sk-[A-Za-z0-9_-]{16,}/;

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p, out);
    else out.push({ path: p, size: st.size });
  }
  return out;
}

function main() {
  if (!fs.existsSync(DIST)) {
    console.error('[FAIL] 找不到构建产物目录：' + DIST);
    return 2;
  }
  const files = walk(DIST);
  const textFiles = files.filter((f) => /\.(js|json|wxml|wxss|html|vue|ts)$/i.test(f.path));
  const counts = Object.fromEntries(WORDS.map((w) => [w, 0]));
  const hits = [];
  let scanned = 0;

  for (const f of textFiles) {
    let content;
    try {
      content = fs.readFileSync(f.path, 'utf8');
    } catch (e) {
      continue;
    }
    scanned += 1;
    const lower = content.toLowerCase();
    for (const w of WORDS) {
      if (w === 'sk-') {
        // sk- 按「密钥样子」精确算，避免把普通文案误计
        const m = content.match(SECRET_LIKE);
        if (m) {
          counts[w] += 1;
          hits.push({ word: w, file: f.path, sample: m[0].slice(0, 8) + '…' });
        }
        continue;
      }
      const c = w.match(/^[a-z.]+$/i) ? (lower.split(w).length - 1) : content.split(w).length - 1;
      if (c > 0) {
        counts[w] += c;
        const idx = lower.indexOf(w.toLowerCase());
        hits.push({ word: w, file: f.path, sample: content.slice(Math.max(0, idx - 30), idx + 30).replace(/\s+/g, ' ') });
      }
    }
  }

  console.log('规则版产物自检：' + DIST);
  console.log('  扫描文本文件：' + scanned + ' 个（共 ' + files.length + ' 个文件）');
  console.log('');
  let bad = 0;
  for (const w of WORDS) {
    const c = counts[w];
    if (c > 0) bad += 1;
    console.log('  ' + (c === 0 ? '[OK]  ' : '[FAIL]') + '  ' + w.padEnd(20) + ' = ' + c);
  }
  if (hits.length) {
    console.log('');
    console.log('命中明细（最多 20 条）：');
    hits.slice(0, 20).forEach((h) => console.log('  - ' + h.word + '  ' + h.file + '  … ' + h.sample));
  }
  console.log('');
  if (bad) {
    console.log('[FAIL] 有 ' + bad + ' 个词不为 0，规则版不能提审');
  } else {
    console.log('[OK] 四个词全部为 0');
  }

  // 规则版不联网：入口页面产物里不得出现联网调用
  console.log('');
  console.log('规则版联网自检（入口页面不得有联网调用）：');
  let netBad = 0;
  for (const rel of NET_PAGES) {
    const p = path.join(DIST, rel);
    if (!fs.existsSync(p)) {
      console.log('  [SKIP] ' + rel + ' 不在包里');
      continue;
    }
    const c = fs.readFileSync(p, 'utf8');
    const found = NET_CALLS.filter((w) => c.indexOf(w) >= 0);
    if (found.length) {
      netBad += 1;
      console.log('  [FAIL] ' + rel + ' 含联网调用：' + found.join(', '));
    } else {
      console.log('  [OK]   ' + rel + ' 无联网调用');
    }
  }
  console.log('');
  if (netBad) {
    console.log('[FAIL] 规则版页面里还有联网调用，违反「不调服务器」');
    return 1;
  }
  console.log('[OK] 规则版入口页面无联网调用');

  // 规则版界面不该出现截图上传（第二节第 2 条）。上传卡已抽成 components/UploadCard.vue，
  // 规则版不引用它，所以这些词不该出现在产物任何文本文件里。
  console.log('');
  console.log('规则版界面自检（不得出现截图上传文案）：');
  let shotBad = 0;
  for (const w of SCREENSHOT_WORDS) {
    const hit = textFiles.find((f) => {
      try {
        return fs.readFileSync(f.path, 'utf8').indexOf(w) >= 0;
      } catch (e) {
        return false;
      }
    });
    if (hit) {
      shotBad += 1;
      console.log('  [FAIL] 产物含「' + w + '」：' + path.relative(DIST, hit.path));
    } else {
      console.log('  [OK]   无「' + w + '」');
    }
  }
  console.log('');
  if (shotBad) {
    console.log('[FAIL] 规则版里出现了截图上传文案，界面应只有粘贴卡');
    return 1;
  }
  console.log('[OK] 规则版界面只有粘贴卡，无截图上传文案');
  return bad ? 1 : 0;
}

process.exit(main());
