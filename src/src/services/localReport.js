// 本地报告拼装：把 DeepSeek 返回的 hits 套固定模板，产出与服务器 report 完全同构的对象。
//
// 报告页、历史记录都按这套字段渲染，所以字段名一个都不能变（对照 engine/schema.py）。
// 所有文字都来自固定模板，不新写文案；报告页因此不会出现「AI」字样。
import { getPattern } from '@/common/patterns.js';
import {
  LOCAL_RULES_VERSION,
  LOCAL_ENGINE,
  SCHEMA_RULES_VERSION,
  PATTERN_DB_VERSION,
} from '@/common/config.js';

// 与 engine/report.py、engine/prompts.py 保持一致，改动时两边一起改
export const DIMENSION_KEYS = ['fee', 'work', 'title', 'pay', 'company', 'contract'];

export const DIM_SHORT = { red: '有问题', amber: '要问清', green: '看着正常', none: '没提到' };

export const OVERALL_SUMMARY = {
  red: '有几处不对劲，先别急着去',
  amber: '有几处要问清楚再决定',
  green: '截图里没看到明显风险',
  unknown: '信息不足，再补一张截图',
};

export const DIMENSION_LABELS = {
  fee: '收费与借贷',
  work: '工作内容',
  title: '岗位名称',
  pay: '薪资待遇',
  company: '公司信息',
  contract: '合同社保',
};

export const GREY_QUESTIONS = {
  fee: '入职前需要我先交任何费用吗？',
  work: '这个岗位每天具体做什么？有没有业绩考核？',
  title: '岗位名称和实际职责一致吗？',
  pay: '底薪是多少？提成怎么算？',
  company: '公司全称是什么？办公地址在哪里？',
  contract: '试用期多久？合同签几年？社保从哪个月开始缴？',
};

export const GREY_QUESTION_TEMPLATE = '截图里没提到「{label}」，可以问 HR：{question}';

export const EMPTY_QUESTIONS = ['请上传包含岗位名称、薪资、工作内容的招聘截图'];

export const EMPTY_VERIFY = ['把岗位详情和 HR 聊天记录一起截图上传，判断更准'];

const LEVEL_RANK = { none: 0, green: 1, amber: 2, red: 3 };

// 套路 level（high/warn/notice）→ finding level（red/amber）
function toFindingLevel(patternLevel) {
  const lv = String(patternLevel || '').toLowerCase();
  if (lv === 'high' || lv === 'red') return 'red';
  if (lv === 'green') return 'green';
  return 'amber';
}

function buildDimensions(findings) {
  return DIMENSION_KEYS.map((key) => {
    const related = findings.filter((f) => f.dimension === key).map((f) => f.level);
    const level = related.length
      ? related.reduce((a, b) => (LEVEL_RANK[b] > LEVEL_RANK[a] ? b : a), 'none')
      : 'none';
    return { key, level, short: DIM_SHORT[level] };
  });
}

function computedOverall(dims, isJob) {
  if (!isJob) return 'unknown';
  const levels = dims.map((d) => d.level);
  if (levels.includes('red')) return 'red';
  if (levels.includes('amber')) return 'amber';
  if (levels.includes('green')) return 'green';
  // 六个维度全是 none：什么都没提到，和服务器保持一致给 unknown（不是 green）
  return 'unknown';
}

// hits: 已通过 validateHits 校验的命中；text: 模型抄录的原文
export function buildLocalReport(raw, hits, text, { minChars = 20 } = {}) {
  const plain = String(text || '');
  const enough = plain.replace(/\s/g, '').length >= minChars;
  const isJob = !!raw && raw.is_job_posting !== false && enough;

  const findings = !isJob
    ? []
    : hits.map((h) => {
        const p = getPattern(h.pattern_id) || {};
        return {
          level: toFindingLevel(p.level),
          dimension: p.dimension || 'work',
          title: p.name || '这条要问清楚',
          evidence: h.evidence,
          context: h.evidence,
          reason: p.why || '',
          source: 'pattern',
          pattern_id: h.pattern_id,
          rule_id: null,
        };
      });

  const dimensions = buildDimensions(findings);
  const overall = computedOverall(dimensions, isJob);

  // 命中套路的 how 作为追问；没提到的维度补固定追问
  const questions = [];
  findings.forEach((f) => {
    const p = getPattern(f.pattern_id);
    if (p && p.how && questions.indexOf(p.how) < 0) questions.push(p.how);
  });
  if (isJob) {
    dimensions.forEach((d) => {
      if (d.level === 'none') {
        const q = GREY_QUESTION_TEMPLATE
          .replace('{label}', DIMENSION_LABELS[d.key] || d.key)
          .replace('{question}', GREY_QUESTIONS[d.key] || '');
        if (q.length <= 60 && questions.indexOf(q) < 0) questions.push(q);
      }
    });
  }

  const verify = [];
  findings.forEach((f) => {
    const p = getPattern(f.pattern_id);
    if (p && p.how && verify.indexOf(p.how) < 0) verify.push(p.how);
  });

  // 严格按 engine/schema.py 的 TOP_KEYS 返回：
  // schema 是白名单校验（多一个字段就报「出现未定义字段」），
  // 所以 engine / ocr_text 这类排查信息**不能放进报告对象**，单独放在第二个返回值里。
  return {
    report: {
      is_job_posting: isJob,
      overall,
      summary: OVERALL_SUMMARY[overall] || OVERALL_SUMMARY.unknown,
      dimensions,
      findings,
      questions_to_ask: questions.slice(0, 5).length ? questions.slice(0, 5) : EMPTY_QUESTIONS,
      how_to_verify: verify.slice(0, 5).length ? verify.slice(0, 5) : EMPTY_VERIFY,
      // 必须是 v主.次：'v3.0+ds' 过不了 schema，标识改放 meta
      rules_version: SCHEMA_RULES_VERSION,
      // 必须是 YYYY-MM-DD：取套路库版本日期
      pattern_db_version: PATTERN_DB_VERSION,
    },
    meta: {
      engine: LOCAL_ENGINE,
      path_tag: LOCAL_RULES_VERSION,   // 'v3.0+ds'，用于核对走的是哪条链路
      ocr_text: plain,
      ocr_source: 'deepseek-vision',
      text_len: plain.replace(/\s/g, '').length,
    },
  };
}
