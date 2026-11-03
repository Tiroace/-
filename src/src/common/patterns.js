// 由 scripts/gen_prompt.py 从 rules/patterns_v1.json 生成，不要手改。
// 来源版本：2026-10-30　条数：58 套路 / 9 套路方案
// 前端只用于「校验模型返回的 pattern_id 是否合法」和「取话术模板」，不做判断。
export const PATTERNS = [
  {
    "pattern_id": "P-FEE-01",
    "name": "入职先交押金",
    "dimension": "fee",
    "level": "red",
    "why": "入职前先收押金、保证金，正规公司不会这么干，交出去很难要回来。",
    "how": "问清有没有任何入职前费用；已交钱就保留凭证并报警/投诉。"
  },
  {
    "pattern_id": "P-FEE-02",
    "name": "服装费自理",
    "dimension": "fee",
    "level": "red",
    "why": "用服装费、工服费名义收钱，是收费类招聘的常见名目。",
    "how": "正规企业工服由公司提供；要求自付就是收费信号。"
  },
  {
    "pattern_id": "P-FEE-03",
    "name": "体检费先付",
    "dimension": "fee",
    "level": "red",
    "why": "入职前让你自己先掏体检费，钱一交很难退。",
    "how": "正规公司一般入职后报销或直接承担体检费。"
  },
  {
    "pattern_id": "P-FEE-04",
    "name": "培训费分期",
    "dimension": "fee",
    "level": "red",
    "why": "以招聘为名收培训费、办分期，工作没找到先背上债。",
    "how": "任何要求先交培训费或签分期的招聘都要立即停下。"
  },
  {
    "pattern_id": "P-FEE-05",
    "name": "垫付货款返利",
    "dimension": "fee",
    "level": "red",
    "why": "先垫钱做任务再返款，是刷单诈骗的标准动作。",
    "how": "凡是需要先垫付的任务一律是诈骗，停止操作并报警。"
  },
  {
    "pattern_id": "P-OVERSEAS-01",
    "name": "境外高薪包机票",
    "dimension": "pay",
    "level": "red",
    "why": "境外高薪加包机票是跨境招工陷阱的典型组合，人身安全风险极高。",
    "how": "核实公司资质与签证类型，不要轻信包机票的境外岗位。"
  },
  {
    "pattern_id": "P-WORK-01",
    "name": "下载陌生App",
    "dimension": "work",
    "level": "red",
    "why": "让你下载陌生 App 做任务，是为了脱离招聘平台监管。",
    "how": "不在官方应用商店上架、要求私下下载的 App 一律不要装。"
  },
  {
    "pattern_id": "P-WORK-02",
    "name": "加客服领任务",
    "dimension": "work",
    "level": "red",
    "why": "招聘流程转到客服微信/QQ群里派单，是刷单诈骗的引流方式。",
    "how": "正规招聘不会让你加个人微信领任务。"
  },
  {
    "pattern_id": "P-WORK-03",
    "name": "到岗再定岗位",
    "dimension": "work",
    "level": "amber",
    "why": "工作内容不写清、到岗再定，实际岗位可能和宣传不一致。",
    "how": "面试前要岗位职责与考核指标写进 offer。"
  },
  {
    "pattern_id": "P-TITLE-01",
    "name": "储备干部做销售",
    "dimension": "title",
    "level": "amber",
    "why": "挂着储备干部/管培生名头，实际是电话销售或地推。",
    "how": "问清每天具体做什么、有没有业绩考核。"
  },
  {
    "pattern_id": "P-TITLE-02",
    "name": "文职实为推广",
    "dimension": "title",
    "level": "amber",
    "why": "行政助理、客服专员等文职名头，实际是推广拉新。",
    "how": "面试时核对岗位名称与工作内容是否一致。"
  },
  {
    "pattern_id": "P-PAY-01",
    "name": "上不封顶",
    "dimension": "pay",
    "level": "amber",
    "why": "「上不封顶」「努力月入过万」这类承诺无法核实。",
    "how": "问清底薪多少、提成怎么算。"
  },
  {
    "pattern_id": "P-PAY-02",
    "name": "薪资跨度大",
    "dimension": "pay",
    "level": "amber",
    "why": "薪资区间跨度太大，大概率是拿最高值吸引人。",
    "how": "问清实际底薪，不要看区间上限。"
  },
  {
    "pattern_id": "P-PAY-03",
    "name": "综合薪资模糊",
    "dimension": "pay",
    "level": "amber",
    "why": "只写「综合薪资」，不写底薪和构成，实际到手可能差很多。",
    "how": "要书面写明底薪、绩效、补贴与发薪日。"
  },
  {
    "pattern_id": "P-COMPANY-01",
    "name": "大公司直招不写名",
    "dimension": "company",
    "level": "amber",
    "why": "不写公司全称、只说大公司直招，无法核实主体。",
    "how": "到国家企业信用信息公示系统按全称查公司。"
  },
  {
    "pattern_id": "P-COMPANY-02",
    "name": "地址含糊",
    "dimension": "company",
    "level": "amber",
    "why": "面试地址含糊或约在酒店、咖啡厅，存在风险。",
    "how": "要求在公司办公地址面试，并提前核实地址。"
  },
  {
    "pattern_id": "P-CONTRACT-01",
    "name": "试用期不缴社保",
    "dimension": "contract",
    "level": "amber",
    "why": "试用期不缴社保违法，社保应从用工之日起缴纳。",
    "how": "签合同前确认社保缴纳起始月份。"
  },
  {
    "pattern_id": "P-CONTRACT-02",
    "name": "押你的证件",
    "dimension": "contract",
    "level": "amber",
    "why": "要求上交或扣押身份证、毕业证原件，不合法。",
    "how": "证件只应查验不应扣留，拒绝交原件。"
  },
  {
    "pattern_id": "P-CONTRACT-03",
    "name": "试用期过长",
    "dimension": "contract",
    "level": "amber",
    "why": "试用期长度可能超过法定上限。",
    "how": "对照《劳动合同法》第十九条核对合同期限与试用期。"
  },
  {
    "pattern_id": "P-FEE-06",
    "name": "先交钱再上岗",
    "dimension": "fee",
    "level": "red",
    "why": "入职前以任何名目收费，都不符合《劳动合同法》。",
    "how": "不交任何入职前费用，保留证据后报警或投诉。"
  },
  {
    "pattern_id": "P-FEE-07",
    "name": "保证金不退",
    "dimension": "fee",
    "level": "red",
    "why": "收保证金还写不退还，正规公司不会收这笔钱。",
    "how": "不要交任何名目的保证金。"
  },
  {
    "pattern_id": "P-FEE-08",
    "name": "入职要交费",
    "dimension": "fee",
    "level": "red",
    "why": "入职前以任何名目收费都不合法。",
    "how": "保留缴费凭证，向劳动监察投诉。"
  },
  {
    "pattern_id": "P-FEE-09",
    "name": "材料费自付",
    "dimension": "fee",
    "level": "red",
    "why": "材料费、建档费是收费名目的变种。",
    "how": "正规公司不会让员工自购材料。"
  },
  {
    "pattern_id": "P-FEE-10",
    "name": "培训押金",
    "dimension": "fee",
    "level": "red",
    "why": "培训押金本质是收费，且很难退回。",
    "how": "不交培训押金，要求写进合同。"
  },
  {
    "pattern_id": "P-FEE-11",
    "name": "薪资先扣费",
    "dimension": "fee",
    "level": "red",
    "why": "从工资里先扣各种费用，实际到手少很多。",
    "how": "问清工资构成与扣款项。"
  },
  {
    "pattern_id": "P-WORK-04",
    "name": "刷单做任务",
    "dimension": "work",
    "level": "red",
    "why": "刷单返利是违法行为，也是最常见的诈骗入口。",
    "how": "立刻停止，不要垫付任何钱。"
  },
  {
    "pattern_id": "P-WORK-05",
    "name": "打字录入兼职",
    "dimension": "work",
    "level": "amber",
    "why": "在家打字、录入快递单这类兼职多为收费或诈骗。",
    "how": "先交钱的录入兼职一律拒绝。"
  },
  {
    "pattern_id": "P-WORK-06",
    "name": "地推发单",
    "dimension": "work",
    "level": "amber",
    "why": "地推发单工作强度大、收入不稳，常与宣传不符。",
    "how": "问清底薪与考核指标。"
  },
  {
    "pattern_id": "P-WORK-07",
    "name": "岗位职责面谈",
    "dimension": "work",
    "level": "amber",
    "why": "职责面谈、到岗再定，容易被安排做销售。",
    "how": "要求 offer 写明岗位职责。"
  },
  {
    "pattern_id": "P-WORK-08",
    "name": "客服实为外呼",
    "dimension": "work",
    "level": "amber",
    "why": "客服岗位实际是电话外呼销售。",
    "how": "问清每天通话量与业绩考核。"
  },
  {
    "pattern_id": "P-WORK-09",
    "name": "先培训再上岗",
    "dimension": "work",
    "level": "amber",
    "why": "先培训后上岗是招转培的常见话术。",
    "how": "确认培训是否收费、是否绑定服务期。"
  },
  {
    "pattern_id": "P-TITLE-03",
    "name": "助理实为电销",
    "dimension": "title",
    "level": "amber",
    "why": "行政/人事助理实为电话销售。",
    "how": "面试时核对岗位与职责。"
  },
  {
    "pattern_id": "P-TITLE-04",
    "name": "管培生地推",
    "dimension": "title",
    "level": "amber",
    "why": "管培生项目实际是地推拉新。",
    "how": "问清晋升路径与考核方式。"
  },
  {
    "pattern_id": "P-TITLE-05",
    "name": "储备干部销售",
    "dimension": "title",
    "level": "amber",
    "why": "储备干部名头实为销售岗。",
    "how": "要求明确岗位名称与职责。"
  },
  {
    "pattern_id": "P-TITLE-06",
    "name": "文职实为销售",
    "dimension": "title",
    "level": "amber",
    "why": "文职岗位实际是销售或客服外呼。",
    "how": "面试前确认工作内容。"
  },
  {
    "pattern_id": "P-PAY-04",
    "name": "日结高薪",
    "dimension": "pay",
    "level": "amber",
    "why": "日结高薪多为夸大宣传，实际难兑现。",
    "how": "问清发薪方式与结算标准。"
  },
  {
    "pattern_id": "P-PAY-05",
    "name": "底薪低提成",
    "dimension": "pay",
    "level": "amber",
    "why": "底薪很低、主要靠提成，实际收入不确定。",
    "how": "问清底薪与提成比例。"
  },
  {
    "pattern_id": "P-PAY-06",
    "name": "综合薪资面议",
    "dimension": "pay",
    "level": "amber",
    "why": "综合薪资、薪资面议，说明待遇不透明。",
    "how": "要求书面写明薪资结构。"
  },
  {
    "pattern_id": "P-PAY-07",
    "name": "包吃住高薪",
    "dimension": "pay",
    "level": "amber",
    "why": "包吃住加高薪的组合常见于招工广告，需核实。",
    "how": "问清住宿条件与扣款。"
  },
  {
    "pattern_id": "P-COMPANY-03",
    "name": "不写公司名",
    "dimension": "company",
    "level": "amber",
    "why": "不写公司全称，无法核实主体。",
    "how": "到企业信用信息公示系统查全称。"
  },
  {
    "pattern_id": "P-COMPANY-04",
    "name": "地址待定",
    "dimension": "company",
    "level": "amber",
    "why": "面试地址待定，存在风险。",
    "how": "要求在公司办公地址面试。"
  },
  {
    "pattern_id": "P-COMPANY-05",
    "name": "酒店面试",
    "dimension": "company",
    "level": "amber",
    "why": "约在酒店、咖啡厅面试，不是正规办公场所。",
    "how": "坚持到公司办公场所面试。"
  },
  {
    "pattern_id": "P-COMPANY-06",
    "name": "大厂外包",
    "dimension": "company",
    "level": "amber",
    "why": "大厂外包岗与直招不同，待遇和归属要说清。",
    "how": "问清劳动合同主体。"
  },
  {
    "pattern_id": "P-CONTRACT-04",
    "name": "不签合同",
    "dimension": "contract",
    "level": "amber",
    "why": "不签劳动合同不合规。",
    "how": "入职一个月内必须签书面合同。"
  },
  {
    "pattern_id": "P-CONTRACT-05",
    "name": "不缴公积金",
    "dimension": "contract",
    "level": "amber",
    "why": "不缴公积金/社保不合规。",
    "how": "确认五险一金缴纳起始月。"
  },
  {
    "pattern_id": "P-CONTRACT-06",
    "name": "押身份证",
    "dimension": "contract",
    "level": "amber",
    "why": "扣押身份证不合法。",
    "how": "证件只应查验，拒绝交原件。"
  },
  {
    "pattern_id": "P-CONTRACT-07",
    "name": "无薪试岗",
    "dimension": "contract",
    "level": "amber",
    "why": "试岗不给工资不符合劳动法。",
    "how": "试岗也应有报酬，保留考勤记录。"
  },
  {
    "pattern_id": "P-FEE-12",
    "name": "押金不退还",
    "dimension": "fee",
    "level": "red",
    "why": "押金、保证金写明不退还，等于白交钱。",
    "how": "不交任何押金；已交保留凭证报警。"
  },
  {
    "pattern_id": "P-WORK-10",
    "name": "刷信誉任务",
    "dimension": "work",
    "level": "red",
    "why": "刷信誉、刷好评任务多为诈骗。",
    "how": "拒绝参与，不要垫付。"
  },
  {
    "pattern_id": "P-COMPANY-07",
    "name": "无营业执照",
    "dimension": "company",
    "level": "amber",
    "why": "没有营业执照或拒绝出示，主体无法核实。",
    "how": "要求出示营业执照并核对名称。"
  },
  {
    "pattern_id": "P-SOFT-01",
    "name": "生活化诱饵",
    "dimension": "work",
    "level": "amber",
    "why": "用轻松、娱乐化的说法吸引人，却不说清楚每天干什么。这类招聘常见于主播、陪玩、引流、娱乐场所等岗位。",
    "how": "每天具体做什么？要不要出镜、陪聊、陪酒？底薪多少，提成怎么算？工作地点在哪？"
  },
  {
    "pattern_id": "P-SOFT-02",
    "name": "岗位名和工作对不上",
    "dimension": "title",
    "level": "amber",
    "why": "岗位名称听起来是坐办公室，实际工作是销售、电销或直播，入职后才发现干的不是一回事。",
    "how": "这个岗位有没有业绩考核？要不要打电话、拉客户、出镜直播？"
  },
  {
    "pattern_id": "P-SOFT-03",
    "name": "只写福利不写工作",
    "dimension": "work",
    "level": "amber",
    "why": "只讲福利、不讲工作，往往是工作内容不好说出口。",
    "how": "能不能把岗位职责写清楚？一天的工作流程是什么样？"
  },
  {
    "pattern_id": "P-SOFT-04",
    "name": "把人往私聊引",
    "dimension": "company",
    "level": "amber",
    "why": "绕开招聘平台私下沟通，平台就管不到了，出了问题很难维权。",
    "how": "能不能在平台里沟通？公司全称和办公地址是什么？"
  },
  {
    "pattern_id": "P-SOFT-05",
    "name": "急招不设门槛",
    "dimension": "pay",
    "level": "amber",
    "why": "门槛很低、待遇很高、还特别着急，正常招聘很少同时出现这三样。",
    "how": "为什么这么急？底薪多少？试用期多久？"
  },
  {
    "pattern_id": "P-SOFT-06",
    "name": "先培训才能上岗",
    "dimension": "work",
    "level": "amber",
    "why": "先培训再上岗，常见的坑是培训收费，或者让你办培训贷。",
    "how": "培训要不要交钱？要不要办分期或贷款？培训期有没有工资？"
  },
  {
    "pattern_id": "P-SOFT-07",
    "name": "工作地点说不清",
    "dimension": "company",
    "level": "amber",
    "why": "工作地点到了才告诉你，你就很难提前核实，也很难中途离开。",
    "how": "具体在哪个城市、什么地址？能不能先发定位？"
  },
  {
    "pattern_id": "P-PROMISE-01",
    "name": "短期暴富承诺",
    "dimension": "pay",
    "level": "red",
    "why": "给出远超行业水平的收入和晋升速度，还打包票「100% 成」，是拉人头、传销、招转培的常见开场。",
    "how": "这几个月晋升的依据是什么？前三个月实际到手多少，能给我看工资条吗？"
  }
];

export const SCHEMES = [
  {
    "scheme_id": "S-01",
    "name": "画饼晋升、拉人头",
    "title": "画饼拉人头",
    "how_harm": "用「几个月升主管」「月入几万到几十万」把你说动，实际靠你拉人来赚钱。",
    "consequence": "先交钱或先拉人，最后钱和人都没了，还可能牵涉传销。",
    "ask": "收入是怎么来的？靠我自己干活，还是靠我拉人？",
    "level": "red"
  },
  {
    "scheme_id": "S-02",
    "name": "培训贷、卖课",
    "title": "培训贷卖课",
    "how_harm": "说包就业，要你先交学费或办分期，合同签的是贷款。",
    "consequence": "工作没找到先背债，每月要还钱，培训内容多是网课。",
    "ask": "培训要不要交钱？能不能不办分期、不给身份证？",
    "level": "red"
  },
  {
    "scheme_id": "S-03",
    "name": "刷单返利",
    "title": "刷单返利",
    "how_harm": "让你先垫钱刷单、做任务，返小钱钓大钱。",
    "consequence": "前几单真返，等你投大的就连本带利提不出来。",
    "ask": "为什么工作需要我先垫钱？能不能只在平台里交易？",
    "level": "red"
  },
  {
    "scheme_id": "S-04",
    "name": "电销保险包装成文职",
    "title": "文职其实是电销",
    "how_harm": "岗位写成客服、行政、助理，实际是打电话卖保险、卖课、拉客户。",
    "consequence": "干的不是招人时说的活，考核不达标就没钱，白耗几个月。",
    "ask": "每天具体做什么？有业绩考核吗？要不要打电话卖东西？",
    "level": "amber"
  },
  {
    "scheme_id": "S-05",
    "name": "主播陪玩引流",
    "title": "陪聊引流当主播",
    "how_harm": "用年轻团队、颜值形象、陪聊天吸引你，实际要出镜陪聊、陪酒、引流。",
    "consequence": "工作内容和承诺完全不符，还可能被要求做不愿做的事。",
    "ask": "要不要出镜、陪聊、陪酒？具体工作时间和内容是什么？",
    "level": "amber"
  },
  {
    "scheme_id": "S-06",
    "name": "无底薪高提成销售",
    "title": "没底薪靠提成",
    "how_harm": "只讲高提成，不谈底薪，卖不出东西就一分钱没有。",
    "consequence": "干满一个月拿不到钱，还倒贴交通和话费。",
    "ask": "有没有底薪？底薪多少？完不成业绩怎么算？",
    "level": "amber"
  },
  {
    "scheme_id": "S-07",
    "name": "境外高薪",
    "title": "境外高薪招人",
    "how_harm": "说东南亚等地月入几万，包机票包吃住，人过去了就收护照。",
    "consequence": "被困在当地从事违法工作，人身安全没有保障。",
    "ask": "具体在哪个国家哪个城市？签证是什么类型？",
    "level": "red"
  },
  {
    "scheme_id": "S-08",
    "name": "入职收费",
    "title": "入职先收钱",
    "how_harm": "用押金、服装费、体检费、安置费等名目，入职前先收钱。",
    "consequence": "钱交出去很难要回来，正规公司入职前不收费。",
    "ask": "入职前需要我先交任何费用吗？",
    "level": "red"
  },
  {
    "scheme_id": "S-00",
    "name": "看起来正常",
    "title": "没看出明显问题",
    "how_harm": "这份信息里没有明显套路，各项写得比较清楚。",
    "consequence": "仍需当面核实公司和劳动合同。",
    "ask": "公司全称是什么？什么时候签劳动合同？",
    "level": "green"
  }
];

export const PATTERN_IDS = new Set(PATTERNS.map((p) => p.pattern_id));

export const SCHEME_IDS = new Set(SCHEMES.map((s) => s.scheme_id));

export function getPattern(id) {
  return PATTERNS.find((p) => p.pattern_id === id) || null;
}

export function getScheme(id) {
  return SCHEMES.find((s) => s.scheme_id === id) || null;
}
