// R3 求助广场自检：开关关闭时入口必须隐藏、页面结构、错误码口径。
// 用法：node miniprogram/scripts/check-r3.mjs
import fs from 'node:fs';
import path from 'node:path';

const SRC = 'D:/qiuzhibilei/src/src';
const rows = [];
const ok = (n, d) => rows.push({ n, pass: true, d: d || '' });
const bad = (n, d) => rows.push({ n, pass: false, d: d || '' });
const read = (p) => fs.readFileSync(path.join(SRC, p), 'utf8');

// ---------- 1. 开关：关闭时入口隐藏，不显示「开发中」 ----------
const square = read('pages/square/index.vue');
const post = read('pages/post/index.vue');
const create = read('pages/post-create/index.vue');
const features = read('common/features.js');
const communityMock = read('services/communityMock.js');

/v-if="!enabled"/.test(square) ? ok('广场列表：社区关闭时整页走隐藏分支') : bad('广场列表没有关闭分支');
/v-if="!enabled"/.test(post) ? ok('求助详情：社区关闭时整页走隐藏分支') : bad('求助详情没有关闭分支');
/v-if="!enabled"/.test(create) ? ok('发起求助：社区关闭时整页走隐藏分支') : bad('发起求助没有关闭分支');

// 明确禁止「开发中」这类占位文案（只查用户可见文案，注释不算）
function stripComments(t) {
  return t.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}
for (const [name, src] of [['广场', square], ['详情', post], ['发起', create]]) {
  const visible = stripComments(src);
  /开发中|建设中|敬请期待|即将上线/.test(visible)
    ? bad(name + '页出现「开发中」类占位文案')
    : ok(name + '页无「开发中」占位文案（用户可见）');
}

// 探测逻辑：404 视为关闭
/isCommunityClosed/.test(features) ? ok('用 404 判定社区是否开放') : bad('没有 404 判定');
/isCommunityClosed/.test(communityMock) || /NOT_FOUND/.test(communityMock)
  ? ok('mock 层关闭时返回 NOT_FOUND（与真后端一致）')
  : bad('mock 层没模拟关闭状态');

// mock 默认关闭
/getStorageSync\(MOCK_ON_KEY\) === '1'/.test(communityMock) ? ok('mock 社区默认关闭（需显式打开）') : bad('mock 社区没有默认关闭');

// ---------- 2. 页面结构 ----------
// 列表：搜索 + 三种排序
/placeholder="搜公司名、岗位或城市"/.test(square) ? ok('列表有搜索框') : bad('列表缺搜索框');
const sortKeys = ['latest', 'active', 'voted'];
sortKeys.every((k) => square.includes("'" + k + "'")) ? ok('列表三种排序齐全（最新/参与最多/我投过的）') : bad('列表排序不全');
/发起求助/.test(square) ? ok('列表有「发起求助」入口') : bad('列表缺发起求助入口');
/只代表个人经历/.test(square) ? ok('列表标注「只代表个人经历」') : bad('列表缺免责标注');

// 详情：投票/理由/经历/举报/申诉
/vote\(1\)/.test(post) && /vote\(-1\)/.test(post) ? ok('详情有建议去/不建议去两个投票按钮') : bad('详情投票按钮缺失');
/我也被要求过交钱/.test(post) ? ok('详情有理由标签') : bad('详情缺理由标签');
/大家的经历/.test(post) ? ok('详情有经历列表') : bad('详情缺经历列表');
/企业申诉入口/.test(post) ? ok('详情有企业申诉入口') : bad('详情缺企业申诉入口');
/提交举报|submitReport/.test(post) ? ok('详情有举报入口') : bad('详情缺举报入口');
/只针对截图内容/.test(post) ? ok('详情标注 AI 结论只针对截图') : bad('详情缺 AI 结论口径');

// 一人一票可改：再点同一项应该取消
/myVote\.value === value \? 0 : value/.test(post) ? ok('一人一票可改（再点取消）') : bad('投票没做改票逻辑');

// 发起求助：必须关联检查记录 + 200 字 + 勾选
/关联检查记录/.test(create) ? ok('发起页要求关联检查记录') : bad('发起页没要求关联记录');
/MAX_Q = 200/.test(create) ? ok('提问上限 200 字') : bad('提问上限不是 200');
/确认是真实经历/.test(create) ? ok('发起页有「确认真实经历」勾选') : bad('发起页缺勾选');
/anonymous = ref\(true\)/.test(create) ? ok('匿名默认打开') : bad('匿名没默认打开');
/补充打码/.test(create) ? ok('发起页有打码预览与补充打码') : bad('发起页缺打码预览');
/写事实，不写「骗子」这类结论/.test(create) ? ok('发起页有「只写事实」提示') : bad('发起页缺撰写提示');

// 发起页：审核说明只写结论，不承诺时效
/审核通过后公开/.test(create) ? ok('发起页有「审核通过后公开」') : bad('发起页缺「审核通过后公开」说明');
{
  const visible = stripComments(create);
  const timingRe = /几分钟|分钟内完成|马上发布|立即发布|即刻公开|小时内完成|秒发布/;
  timingRe.test(visible)
    ? bad('发起页出现审核时效承诺：' + (visible.match(timingRe) || [''])[0])
    : ok('发起页无审核时效承诺');
}

// ---------- 3. 错误码口径（docs/10 3.3） ----------
const apiSrc = read('services/api.js');
const errCodes = ['NEW_ACCOUNT_RESTRICTED', 'CONTENT_BLOCKED', 'FORBIDDEN', 'NOT_FOUND'];
const missing = errCodes.filter((c) => !post.includes(c) && !create.includes(c));
missing.length ? bad('页面没处理错误码：' + missing.join('/')) : ok('四个社区错误码都有大白话提示');
/NEW_ACCOUNT_RESTRICTED: '账号注册还不满 24 小时/.test(post) ? ok('新号 24h 限制文案准确') : bad('新号限制文案缺失');

// ---------- 4. 接口对齐 docs/10 ----------
const needPaths = [
  "'/community/posts'",
  "'/community/appeals'",
  '/community/posts/',
];
needPaths.every((p) => apiSrc.includes(p)) ? ok('api.js 有社区接口') : bad('api.js 缺社区接口');
/c\/vote|'\/vote'/.test(apiSrc) ? ok('投票接口路径正确') : bad('缺投票接口');
/'\/experiences'/.test(apiSrc) ? ok('经历接口路径正确') : bad('缺经历接口');
/'\/report'/.test(apiSrc) ? ok('举报接口路径正确') : bad('缺举报接口');

// ---------- 5. 视觉：新页面无写死色值 ----------
for (const [name, src] of [['广场', square], ['详情', post], ['发起', create]]) {
  const style = (src.match(/<style[^>]*>([\s\S]*?)<\/style>/) || [, ''])[1];
  /#[0-9A-Fa-f]{3,8}\b|rgba?\(/.test(style) ? bad(name + '页有写死色值') : ok(name + '页写死色值 = 0');
}

// ---------- 6. pages.json 注册 ----------
const pagesJson = JSON.parse(read('pages.json'));
const routes = (pagesJson.pages || []).map((p) => p.path);
['pages/square/index', 'pages/post/index', 'pages/post-create/index'].every((r) => routes.includes(r))
  ? ok('三个社区页面都已注册')
  : bad('社区页面注册不全');

// 输出
let failed = 0;
for (const r of rows) {
  if (!r.pass) failed += 1;
  console.log((r.pass ? '  ✓ ' : '  ✗ ') + r.n + (r.d ? '  → ' + r.d : ''));
}
console.log('\n共 ' + rows.length + ' 项，通过 ' + (rows.length - failed) + ' 项，失败 ' + failed + ' 项');
process.exit(failed === 0 ? 0 : 1);
