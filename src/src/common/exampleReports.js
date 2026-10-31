// 示例报告数据（由 miniprogram/scripts/gen-example-reports.py 生成，不要手改）
// 来源：确定性引擎实际跑出的 v2 报告（优先 data/examples 标准示例），与真实引擎输出同构。
// 用途：报告页 4 种 overall 形态展示与自测；内容是测试样本，不指向任何真实企业。
export const EXAMPLE_REPORTS = {
  "red": {
    "is_job_posting": true,
    "overall": "red",
    "summary": "有几处不对劲，先别急着去",
    "dimensions": [
      {
        "key": "fee",
        "level": "red",
        "short": "有问题"
      },
      {
        "key": "work",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "title",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "pay",
        "level": "green",
        "short": "看着正常"
      },
      {
        "key": "company",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "contract",
        "level": "none",
        "short": "没提到"
      }
    ],
    "findings": [
      {
        "level": "red",
        "dimension": "fee",
        "title": "先交押金",
        "evidence": "入职须知：需交押金 300 元，工作满三个月退还",
        "context": "入职须知：需交押金 300 元，工作满三个月退还",
        "reason": "入职前就收押金、保证金或服装费，正规公司不会这样收费，钱交出去很难要回来。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-DEPOSIT-01"
      },
      {
        "level": "red",
        "dimension": "fee",
        "title": "先交押金",
        "evidence": "另外收取服装费 150 元、工牌费 20 元",
        "context": "另外收取服装费 150 元、工牌费 20 元",
        "reason": "入职前就收押金、保证金或服装费，正规公司不会这样收费，钱交出去很难要回来。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-DEPOSIT-01"
      },
      {
        "level": "red",
        "dimension": "fee",
        "title": "先交钱再上岗",
        "evidence": "名额有限，先到先得",
        "context": "名额有限，先到先得",
        "reason": "入职前以任何名目收费，都不符合《劳动合同法》。",
        "source": "pattern",
        "pattern_id": "P-FEE-06",
        "rule_id": null
      },
      {
        "level": "green",
        "dimension": "pay",
        "title": "薪资写清楚",
        "evidence": "薪资：4800-5500 元/月，包吃住",
        "context": "薪资：4800-5500 元/月，包吃住",
        "reason": "薪资区间和结构写得比较具体，不像是随口画的饼。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-GREEN-PAY-01"
      }
    ],
    "questions_to_ask": [
      "入职前需要我先交任何费用吗？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「公司信息」，可以问 HR：公司全称是什么？办公地址在哪里？",
      "截图里没提到「合同社保」，可以问 HR：试用期多久？合同签几年？社保从哪个月开始缴？"
    ],
    "how_to_verify": [
      "正规企业不会向求职者收费；遇到要求转账、索要验证码，立即拨打 110 或 96110"
    ],
    "pattern_db_version": "2026-10-30",
    "rules_version": "v2.0",
    "report_id": "SAMPLE-RED"
  },
  "amber": {
    "is_job_posting": true,
    "overall": "amber",
    "summary": "有几处要问清楚再决定",
    "dimensions": [
      {
        "key": "fee",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "work",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "title",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "pay",
        "level": "amber",
        "short": "要问清"
      },
      {
        "key": "company",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "contract",
        "level": "amber",
        "short": "要问清"
      }
    ],
    "findings": [
      {
        "level": "amber",
        "dimension": "contract",
        "title": "试用期超限",
        "evidence": "合同期一年，试用期六个月",
        "context": "合同期一年，试用期六个月",
        "reason": "试用期长度可能超过法定上限，签合同前要核对合同期限。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-PROBATION-01"
      },
      {
        "level": "amber",
        "dimension": "pay",
        "title": "薪资跨度大",
        "evidence": "试用期间工资 3000 元，转正后 3800 元",
        "context": "试用期间工资 3000 元，转正后 3800 元",
        "reason": "薪资区间跨度太大，大概率是拿最高值吸引人。",
        "source": "pattern",
        "pattern_id": "P-PAY-02",
        "rule_id": null
      }
    ],
    "questions_to_ask": [
      "底薪是多少？提成怎么算？",
      "试用期多久？合同签几年？社保从哪个月开始缴？",
      "截图里没提到「收费与借贷」，可以问 HR：入职前需要我先交任何费用吗？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「公司信息」，可以问 HR：公司全称是什么？办公地址在哪里？"
    ],
    "how_to_verify": [
      "要求书面写明底薪、绩效、补贴和发薪日",
      "对照《劳动合同法》第十九条核对试用期；签合同前确认社保缴纳起始月"
    ],
    "pattern_db_version": "2026-10-30",
    "rules_version": "v2.0",
    "report_id": "SAMPLE-AMBER"
  },
  "green": {
    "is_job_posting": true,
    "overall": "green",
    "summary": "目前看没大问题，可以去",
    "dimensions": [
      {
        "key": "fee",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "work",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "title",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "pay",
        "level": "green",
        "short": "看着正常"
      },
      {
        "key": "company",
        "level": "green",
        "short": "看着正常"
      },
      {
        "key": "contract",
        "level": "none",
        "short": "没提到"
      }
    ],
    "findings": [
      {
        "level": "green",
        "dimension": "company",
        "title": "公司写得全",
        "evidence": "公司名称：青岛海联信息技术有限公司",
        "context": "公司名称：青岛海联信息技术有限公司",
        "reason": "截图里写了公司名称或地址，公司主体查得到。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-GREEN-COMPANY-01"
      },
      {
        "level": "green",
        "dimension": "pay",
        "title": "薪资写清楚",
        "evidence": "薪资：15000-20000 元/月，五险一金，周末双休",
        "context": "薪资：15000-20000 元/月，五险一金，周末双休",
        "reason": "薪资区间和结构写得比较具体，不像是随口画的饼。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-GREEN-PAY-01"
      }
    ],
    "questions_to_ask": [
      "这个岗位的日常工作内容是什么？",
      "工资结构和发薪时间怎么安排？",
      "截图里没提到「收费与借贷」，可以问 HR：入职前需要我先交任何费用吗？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「合同社保」，可以问 HR：试用期多久？合同签几年？社保从哪个月开始缴？"
    ],
    "how_to_verify": [
      "到国家企业信用信息公示系统核对公司信息",
      "面试地点选在公司办公场所，不去酒店或私人住所"
    ],
    "pattern_db_version": "2026-10-30",
    "rules_version": "v2.0",
    "report_id": "SAMPLE-GREEN"
  },
  "unknown": {
    "is_job_posting": false,
    "overall": "unknown",
    "summary": "信息不足，再补一张截图",
    "dimensions": [
      {
        "key": "fee",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "work",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "title",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "pay",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "company",
        "level": "none",
        "short": "没提到"
      },
      {
        "key": "contract",
        "level": "none",
        "short": "没提到"
      }
    ],
    "findings": [],
    "questions_to_ask": [
      "请上传包含岗位名称、薪资、工作内容的招聘截图"
    ],
    "how_to_verify": [
      "把岗位详情和 HR 聊天记录一起截图上传，判断更准"
    ],
    "rules_version": "v2.0",
    "pattern_db_version": "2026-10-30",
    "report_id": "SAMPLE-UNKNOWN"
  }
};

export function getExampleReport(overall) {
  return EXAMPLE_REPORTS[overall] || null;
}
