// 风险等级、风险类型、结论口径的展示映射。
// 合规要求（下派书 §8）：只用「风险提示」「疑似」「建议核实」，不用定性词。
export const RISK_LEVEL_LABEL = {
  high: '高风险提示',
  warn: '需要警惕',
  notice: '需要留意',
  safe: '较安全',
  unknown: '信息不足',
};

export const RISK_LEVEL_CLASS = {
  high: 'level-high',
  warn: 'level-warn',
  notice: 'level-notice',
  safe: 'level-safe',
  unknown: 'level-unknown',
};

// 风险等级配色：只留「用哪个变量」的映射名，实际色值在 uni.scss 里（页面不写死色值）
// v1 的浅色底已废弃（改版后是深色「夜间信号」体系），保留 key 以便旧数据兜底。
export const RISK_LEVEL_BG = {
  high: 'red-soft',
  warn: 'amber-soft',
  notice: 'amber-soft',
  safe: 'green-soft',
  unknown: 'surface',
};

export const RISK_TYPE_LABEL = {
  scam: '疑似招聘诈骗',
  train_loan: '疑似招转培 / 培训贷',
  bait_switch: '疑似岗位名实不符',
  exaggerate: '疑似夸大宣传',
  illegal_clause: '疑似违规条款',
  normal: '未发现明显风险',
};

export const VERDICT_LABEL = {
  '不建议前往': '建议谨慎，暂时不要去面试',
  '先核实再去': '建议先核实，再去面试',
  '可以去，带着问题去': '可以去面试，带着问题去',
  '可以去': '可以去面试',
  '信息不足': '信息不足，请补充截图',
};

// 高危报告强制显示的求助提示（下派书 §8）
// 注意：12333 单独一行文字展示（D21，不做拨号键），这里不再重复列出，避免文案打架
export const HELP_TIPS = [
  '不要给对方转账，不要交任何押金、服装费、培训费。',
  '怀疑遇到诈骗，可以拨打 110 报警，或打 96110 反诈专线。',
];

// D20 定稿：带后半句的版本（全产品唯一版本，报告页/示例报告/协议/提审材料同批对齐）
export const DISCLAIMER_TEXT =
  '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。';

// 全局禁用词（下派书 §8）。渲染报告前做一次过滤兜底，
// 服务端已经过滤过一次，这里是前端第二道保险。
export const FORBIDDEN_WORDS = [
  '骗子公司',
  '黑心企业',
  '100%识别',
  '100% 识别',
  '最准',
  '绝对安全',
  '一定被骗',
];

export function safeText(input, fallback = '') {
  if (input === null || input === undefined) return fallback;
  let text = String(input);
  FORBIDDEN_WORDS.forEach((word) => {
    if (text.includes(word)) {
      text = text.split(word).join('（已屏蔽词）');
    }
  });
  return text;
}

export function levelLabel(level) {
  return RISK_LEVEL_LABEL[level] || '未知';
}

export function verdictLabel(verdict) {
  return VERDICT_LABEL[verdict] || verdict || '信息不足';
}

export function typeLabel(type) {
  return RISK_TYPE_LABEL[type] || '其他风险';
}
