// 报告页 v2 自测：验证 docs/06 05 号文案里的硬性规则在代码里成立。
// 用法：node --import ./tests/register-alias.mjs miniprogram/scripts/check-report-v2.mjs
import fs from 'node:fs';
import path from 'node:path';

const SRC = 'D:/qiuzhibilei/src/src';
const rows = [];
const ok = (n, d) => rows.push({ n, pass: true, d: d || '' });
const bad = (n, d) => rows.push({ n, pass: false, d: d || '' });

const reportVue = fs.readFileSync(SRC + '/pages/report/index.vue', 'utf8');
const exampleSrc = fs.readFileSync(SRC + '/common/exampleReports.js', 'utf8');

// 1. 免责声明：D20 定稿（带后半句，不带 AI 字样）
const D20 =
  '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。';
{
  const constantsSrc = fs.readFileSync(SRC + '/common/constants.js', 'utf8');
  constantsSrc.includes(D20) ? ok('免责声明 = D20 定稿原文（constants.js）') : bad('constants.js 不是 D20 原文');
  // 全项目只允许 constants.js 定义一份
  // 开发自测页里那份是「比对基准」（自检用，不渲染给用户），且该页不进正式包，排除
  const dupes = [];
  const walkAll = (d) => {
    for (const f of fs.readdirSync(d)) {
      const p = path.join(d, f);
      if (fs.statSync(p).isDirectory()) walkAll(p);
      else if (/\.vue$/.test(f)) {
        const rel = path.relative(SRC, p).replace(/\\/g, '/');
        if (rel.indexOf('pages/dev/') === 0) continue;
        const t = fs.readFileSync(p, 'utf8');
        if (t.includes('本报告由系统根据截图文字和规则库自动生成')) dupes.push(rel);
      }
    }
  };
  walkAll(SRC);
  dupes.length ? bad('免责声明有多份副本：' + dupes.join(', ')) : ok('免责声明全项目只有一份（constants.js，dev 页比对基准除外）');
}
/(?<![A-Za-z])AI(?![A-Za-z])/.test(reportVue) ? bad('报告页仍含 AI 字样') : ok('报告页无 AI 字样');

// 2. 4 种 overall 标题
const titles = {
  red: '这份工作，建议先别去',
  amber: '先问清楚，再决定去不去',
  green: '截图里没看到明显风险',
  unknown: '截图信息不够，再补一张',
};
for (const [k, v] of Object.entries(titles)) {
  reportVue.includes(v) ? ok('overall=' + k + ' 标题：' + v) : bad('缺 overall=' + k + ' 的标题');
}

// 3. 灰灯固定文案
reportVue.includes('截图里没提到') ? ok('灰灯文案 = 截图里没提到') : bad('灰灯文案缺失');
// 禁止同一函数里返回「正常/无风险」
const noneFn = (reportVue.match(/function dimShort[\s\S]*?\n}/) || [''])[0];
/正常|无风险|待补充|未发现|暂无|没问题/.test(noneFn) ? bad('灰灯写了禁用写法') : ok('灰灯禁用写法 0 处');

// 4. 来源标签只剩两种（路线令：不用大模型，没有「AI 推理」）
for (const label of ['规则命中', '套路库匹配']) {
  const inBrand = fs.readFileSync(SRC + '/common/brand.js', 'utf8').includes(label);
  inBrand ? ok('来源标签：' + label) : bad('缺来源标签：' + label);
}
fs.readFileSync(SRC + '/common/brand.js', 'utf8').includes('AI 推理')
  ? bad('来源标签仍有「AI 推理」')
  : ok('来源标签无「AI 推理」（路线令只留 rule/pattern）');

// 5. evidence 必须在 context 里才上屏（证据可追溯底线）
/context\)\.includes\(String\(f\.evidence\)\)/.test(reportVue.replace(/\s+/g, ''))
  ? ok('evidence 不在 context 中的条目不显示')
  : bad('缺少 evidence 可追溯过滤');

// 6. 已交钱区块只在 red 出现
/v-if="overall === 'red'"/.test(reportVue) ? ok('已交钱区块仅 overall=red') : bad('已交钱区块条件不对');
reportVue.includes('110') && reportVue.includes('96110') ? ok('拨打 110 / 96110') : bad('缺 110/96110');

// 6b. D21 口径：110 / 96110 是拨号按钮；12333 只做文字提示，不做拨号键
{
  const nums = ['110', '96110', '12333'];
  const missing = nums.filter((n) => !reportVue.includes(n));
  missing.length ? bad('高危区块缺号码：' + missing.join('/')) : ok('三个号码齐全：110 / 96110 / 12333');

  // 只有 110 和 96110 可拨号
  const call110 = /callPhone\('110'\)/.test(reportVue);
  const call96110 = /callPhone\('96110'\)/.test(reportVue);
  call110 && call96110 ? ok('110 / 96110 是拨号按钮') : bad('110 或 96110 不能拨号');

  // 12333 绝对不能是拨号键（D21：避免用户误以为能追回被骗的钱）
  const call12333 = /callPhone\('12333'\)/.test(reportVue);
  call12333 ? bad('12333 仍做成拨号键（D21 要求只做文字）') : ok('12333 不是拨号键（符合 D21）');

  // 12333 必须是文字，且文案含「劳动权益」
  const labourLine = (reportVue.match(/劳动权益[^<]*12333|12333[^<]*/g) || []).join('');
  /劳动权益/.test(reportVue) ? ok('12333 标注为劳动权益热线') : bad('12333 缺口径说明');
  /欠薪|不缴社保|扣押证件/.test(reportVue) ? ok('12333 标明适用场景（欠薪/不缴社保/扣押证件）') : bad('12333 没写适用场景');

  // 必须从 constants.js 引入 HELP_TIPS 与免责声明
  /import \{[^}]*HELP_TIPS[^}]*\} from '@\/common\/constants\.js'/.test(reportVue)
    ? ok('HELP_TIPS 从 constants.js 正确引入')
    : bad('HELP_TIPS 没有正确 import（会静默不渲染）');
}

// 6c. D20 免责声明：报告页必须引用 constants 的常量，不能自己再写一份
{
  const hasLocalCopy = /const DISCLAIMER =/.test(reportVue);
  hasLocalCopy ? bad('报告页自己写了一份免责声明（会与 constants 不同步）') : ok('免责声明统一引用 constants（无重复副本）');
  /DISCLAIMER_TEXT/.test(reportVue) ? ok('报告页从 constants 引入 DISCLAIMER_TEXT') : bad('报告页没引用 DISCLAIMER_TEXT');
}

// 7. 复制问题
reportVue.includes('已复制，可以直接发给 HR') ? ok('复制成功提示正确') : bad('复制提示不对');

// 8. 复制内容必须是全部问题（不截断）
/q\s*=\s*allQuestions\.value\.join/.test(reportVue.replace(/\n/g, '')) || /allQuestions\.value\.join\('\\n'\)/.test(reportVue)
  ? ok('复制的是全部问题（不止前 5 条）')
  : bad('复制只复制了展示的部分');

// 9. green 标题不含「安全/没问题/放心」以外的问题
const greenTitle = titles.green;
/安全|放心/.test(greenTitle) ? bad('green 标题含禁用词') : ok('green 标题无「安全/放心」');

// 10. 示例数据：4 种 overall 齐全
for (const k of ['red', 'amber', 'green', 'unknown']) {
  exampleSrc.includes('"' + k + '"') ? ok('示例数据含 ' + k) : bad('示例数据缺 ' + k);
}

// 11. 示例数据里 6 维齐全且 short ≤6
const m = exampleSrc.match(/export const EXAMPLE_REPORTS =\s*([\s\S]*?);\s*\n\s*export function/);
if (m) {
  // 用 eval 安全地取对象（本地文件，内容可控）
  // eslint-disable-next-line no-eval
  const obj = eval('(' + m[1] + ')');
  let dimOk = true;
  let shortOk = true;
  for (const [k, rep] of Object.entries(obj)) {
    const keys = (rep.dimensions || []).map((d) => d.key);
    if (keys.length !== 6) dimOk = false;
    for (const d of rep.dimensions || []) {
      if (d.level !== 'none' && d.short && d.short.length > 6) {
        shortOk = false;
        rows.push({ n: 'short 超 6 字：' + k + '/' + d.key + '=' + d.short, pass: false });
      }
    }
  }
  dimOk ? ok('示例报告都是 6 维齐全') : bad('示例报告维度不是 6 项');
  shortOk ? ok('示例报告 short 均 ≤6 字') : null;
} else {
  bad('解析不到示例报告数据');
}

// 12. 页面无写死色值
const style = (reportVue.match(/<style[^>]*>([\s\S]*?)<\/style>/) || [, ''])[1];
/#[0-9A-Fa-f]{3,8}\b|rgba?\(/.test(style) ? bad('报告页还有写死色值') : ok('报告页写死色值 = 0');

// 输出
let failed = 0;
for (const r of rows) {
  if (!r.pass) failed += 1;
  console.log((r.pass ? '  ✓ ' : '  ✗ ') + r.n + (r.d ? '  → ' + r.d : ''));
}
console.log('\n共 ' + rows.length + ' 项，通过 ' + (rows.length - failed) + ' 项，失败 ' + failed + ' 项');
process.exit(failed === 0 ? 0 : 1);
