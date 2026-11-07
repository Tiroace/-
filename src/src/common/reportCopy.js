// 报告页与报告模板里「跟载体有关的措辞」：规则版是粘贴文字，识图版是上传截图。
//
// 为什么单独放一个文件：
// 同一句话在报告页模板、localReport 模板、示例报告里各出现一次，散落着改必然漏。
// 老板 2026-11-07 明确要求规则版画面上不能出现「上传截图」这类字（提审截图要用），
// 所以凡是带「截图/文字」的措辞都从这里取，两版按 ENGINE 自动选。
//
// 规则版用词规范（老板原文）：依据你提供的文字 / 文字里没看到明显风险 /
// 文字里没提到 / 这段文字里没发现具体问题。识图版保留截图措辞。
import { VISION_ENGINE } from '@/common/config.js';

export const IS_IMAGE = VISION_ENGINE;

// 报告页「依据」行前半句
export const BASIS_PREFIX = IS_IMAGE ? '依据你上传的截图' : '依据你提供的文字';

// 四种结论标题（green / unknown 带载体词）
export const VERDICT_TITLE = {
  red: '这份工作，建议先别去',
  amber: '先问清楚，再决定去不去',
  green: IS_IMAGE ? '截图里没看到明显风险' : '文字里没看到明显风险',
  unknown: IS_IMAGE ? '截图信息不够，再补一张' : '信息不够，再补充一些文字',
};

// unknown 时的副标题
export const UNKNOWN_SUB = IS_IMAGE
  ? '截图里没读到岗位、薪资、公司这些关键信息'
  : '文字里没读到岗位、薪资、公司这些关键信息';

// 灰灯（某维度没提到）
export const DIM_NONE_TEXT = IS_IMAGE ? '截图里没提到' : '文字里没提到';

// 没有任何发现时的提示
export const EMPTY_FINDINGS = IS_IMAGE ? '这张截图里没发现具体问题' : '这段文字里没发现具体问题';
export const EMPTY_FINDINGS_UNKNOWN = IS_IMAGE ? '截图里没读到能判断的内容' : '文字里没读到能判断的内容';

// 公司核实卡片右上角来源标签
export const CORP_SOURCE_TAG = IS_IMAGE ? '来自截图' : '来自你提供的文字';

// 报告模板里的固定文案（localReport.js 用）
export const OVERALL_SUMMARY = {
  red: '有几处不对劲，先别急着去',
  amber: '有几处要问清楚再决定',
  green: IS_IMAGE ? '截图里没看到明显风险' : '文字里没看到明显风险',
  unknown: IS_IMAGE ? '信息不足，再补一张截图' : '信息不足，再补充一些文字',
};

export const GREY_QUESTION_TEMPLATE = IS_IMAGE
  ? '截图里没提到「{label}」，可以问 HR：{question}'
  : '文字里没提到「{label}」，可以问 HR：{question}';

export const EMPTY_QUESTIONS = IS_IMAGE
  ? ['请上传包含岗位名称、薪资、工作内容的招聘截图']
  : ['请粘贴包含岗位名称、薪资、工作内容的招聘信息'];

export const EMPTY_VERIFY = IS_IMAGE
  ? ['把岗位详情和 HR 聊天记录一起截图上传，判断更准']
  : ['把岗位介绍和 HR 聊天一起粘贴，判断更准'];
