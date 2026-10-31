// 品牌与全局常量（改名后集中在这里，页面不要再写死名称）
export const APP_NAME = '面试请等等';
export const APP_VERSION = '2.0.0';

// 原生组件的颜色属性只能用字面量（switch 的 color=<string>），
// 集中放这里，页面不散落色值；值与 uni.scss 的 $cta 保持一致。
export const SWITCH_COLOR = '#FFC93C';

// 分享标题：不带任何公司名（合规要求 §8）
export const SHARE_TITLE = '去面试之前，先让它看一眼';
export const SHARE_SUBTITLE = '招聘截图发过来，30 秒告诉你这份工作有没有坑。';

// 六个检查维度（任务书 §4.3，固定）
export const DIMENSIONS = [
  { key: 'fee', name: '收费与借贷' },
  { key: 'work', name: '工作内容' },
  { key: 'title', name: '岗位名称' },
  { key: 'pay', name: '薪资待遇' },
  { key: 'company', name: '公司信息' },
  { key: 'contract', name: '合同社保' },
];

// 整体结论（overall）→ 标题与配色变量名
export const OVERALL = {
  red: { title: '这份工作，建议先别去', lamp: 'red' },
  amber: { title: '先问清楚，再决定去不去', lamp: 'amber' },
  green: { title: '看起来没问题，可以去', lamp: 'green' },
  unknown: { title: '截图信息不够，再补一张', lamp: 'off' },
};

// 发现来源标签（任务书 §6.3）
export const SOURCE_LABEL = {
  rule: '规则命中',
  pattern: '套路库匹配',
};

// 灯色 → 中文
export const LEVEL_LABEL = {
  red: '红灯',
  amber: '黄灯',
  green: '绿灯',
  none: '没提到',
};
