// 规则版（本地）自检：node --import ./tests/register-alias.mjs tests/check-rules.mjs
//
// 这部分不联网、不依赖手机，直接用红/黄/绿三类典型截图文字验证：
//   1) 红：交押金 + 境外高薪 + 零工 → 必须红
//   2) 黄：储备干部做销售 → 必须黄
//   3) 绿：正常岗位 → 必须绿，且不能因为正常薪资被判套路
//   4) 不是招聘截图 → unknown，不扣次数
//   5) 变形写法（薇信 / 押 金 / 繁体）都认得出
//   6) 同一段文字跑两次结果完全一样（确定性）
import assert from 'node:assert';
import { buildRuleReport, normalizeText, parseSalary, isRecruitText } from '../src/services/rules.js';

let pass = 0;
let fail = 0;
function check(name, fn) {
  try {
    fn();
    pass += 1;
    console.log('  [OK]  ' + name);
  } catch (e) {
    fail += 1;
    console.log('  [FAIL] ' + name + '  →  ' + e.message);
  }
}

const RED_TEXT = [
  '诚招操作工 待遇优厚',
  '月薪8000-30000元，上不封顶，轻松月入过万',
  '入职需交押金300元，服装费自理',
  '工作地点：缅甸，包机票包吃住，月入2万',
  '联系人：薇信 abc123',
].join('\n');

const AMBER_TEXT = [
  '招聘储备干部 5名',
  '岗位职责：负责电话回访客户，完成销售业绩考核',
  '薪资：底薪3000-8000元，综合薪资按国家规定',
  '要求：无需经验，零基础可培训',
  '公司地址：本市某大厦',
].join('\n');

const GREEN_TEXT = [
  '东风科技有限公司 招聘 前端开发工程师',
  '岗位职责：负责公司后台系统的开发、协助测试、整理技术文档',
  '薪资：15000-18000元/月',
  '试用期3个月，签订劳动合同，缴纳五险一金',
  '工作地点：深圳市南山区科技园某某大厦8楼',
].join('\n');

const NONJOB_TEXT = '这是一张风景照片，上面写着今天天气很好，我去公园散步了，心情不错。';

console.log('规则版自检');

check('红灯：交押金 + 境外高薪 + 月入过万 → 红', () => {
  const r = buildRuleReport(RED_TEXT).report;
  assert.strictEqual(r.overall, 'red', '实际 ' + r.overall);
  assert.ok(r.findings.length >= 3, '发现太少 ' + r.findings.length);
  assert.ok(r.findings.some((f) => f.rule_id === 'R-FEE-01'), '没抓到押金');
  assert.ok(r.findings.every((f) => f.source === 'rule' || f.source === 'pattern'), 'source 只能是 rule/pattern');
});

check('黄灯：储备干部做销售 → 黄', () => {
  const r = buildRuleReport(AMBER_TEXT).report;
  assert.strictEqual(r.overall, 'amber', '实际 ' + r.overall);
  assert.ok(r.findings.some((f) => f.rule_id === 'R-TITLE-A01'), '没抓到岗位名不符');
});

check('绿灯：正常岗位 → 绿，且不误判薪资', () => {
  const r = buildRuleReport(GREEN_TEXT).report;
  assert.strictEqual(r.overall, 'green', '实际 ' + r.overall + ' 发现=' + JSON.stringify(r.findings.map((f) => f.rule_id || f.pattern_id)));
  assert.strictEqual(r.findings.length, 0, '正常岗位不该有发现');
});

check('不是招聘截图 → unknown，is_job_posting=false', () => {
  const r = buildRuleReport(NONJOB_TEXT).report;
  assert.strictEqual(r.overall, 'unknown');
  assert.strictEqual(r.is_job_posting, false);
});

check('字数太少（<20）→ unknown', () => {
  const r = buildRuleReport('招聘 押金 300');
  assert.strictEqual(r.report.is_job_posting, false);
});

check('变形写法：薇信→微信、押 金→押金、繁体→简体', () => {
  const t = normalizeText('入職需繳押 金300元，請加薇信聯絡');
  assert.ok(t.indexOf('押金') >= 0, '押金没规整：' + t);
  assert.ok(t.indexOf('微信') >= 0, '微信没规整：' + t);
  assert.ok(t.indexOf('入职') >= 0, '繁体没转：' + t);
});

check('工资解析：8000-20000 / 8k-2w / 8千到1.5万 / 日结200-500', () => {
  const a = parseSalary('月薪8000-20000元');
  assert.deepStrictEqual([a.lo, a.hi], [8000, 20000]);
  const b = parseSalary('薪资 8k-2w');
  assert.deepStrictEqual([b.lo, b.hi], [8000, 20000]);
  const c = parseSalary('工资 8千到1.5万');
  assert.deepStrictEqual([c.lo, c.hi], [8000, 15000]);
  const d = parseSalary('日结200-500元');
  assert.deepStrictEqual([d.lo, d.hi, d.daily], [4400, 11000, true]);
});

check('薪资跨度 2.5 倍以上 → 黄灯规则命中', () => {
  const r = buildRuleReport('招聘客服\n薪资 3000-12000元\n岗位职责：负责接听客户电话')[0];
  const x = buildRuleReport('招聘客服\n薪资 3000-12000元\n岗位职责：负责接听客户电话').report;
  assert.ok(x.findings.some((f) => f.rule_id === 'R-PAY-A01'), '没抓到薪资跨度');
});

check('确定性：同一段文字跑两次结果一样', () => {
  const a = JSON.stringify(buildRuleReport(RED_TEXT));
  const b = JSON.stringify(buildRuleReport(RED_TEXT));
  assert.strictEqual(a, b);
});

check('报告结构：九项齐全，rules_version 规范值', () => {
  const { report, meta } = buildRuleReport(GREEN_TEXT);
  assert.deepStrictEqual(Object.keys(report).sort(), [
    'dimensions', 'findings', 'how_to_verify', 'is_job_posting', 'overall',
    'pattern_db_version', 'questions_to_ask', 'rules_version', 'summary',
  ].sort());
  assert.strictEqual(report.rules_version, 'v3.0');
  assert.strictEqual(meta.path_tag, 'v3.0-local');
  assert.strictEqual(meta.engine, 'rules');
});

check('招聘关键词判定：有岗位/薪资/面试等字样才算招聘', () => {
  assert.strictEqual(isRecruitText('招聘信息：本岗位薪资面议，面试通过后入职上班，HR会联系你'), true);
  assert.strictEqual(isRecruitText('今天天气不错，我去公园走了一圈，看到了很多花和树，心情很好'), false);
});

console.log('');
console.log(pass + ' 项通过，' + fail + ' 项失败');
if (fail) process.exit(1);
