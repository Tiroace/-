// 示例报告数据（由 src/scripts/gen-example-reports.py 生成，不要手改）
// 来源：src/scripts/example-samples.json 的固定虚构样本，逐条跑确定性引擎得到。
// 版本号取 engine/prompts.py 的 RULES_VERSION，与真实引擎输出同构。
// 内容是虚构的，不指向任何公司。
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
    "findings": [
      {
        "level": "red",
        "dimension": "fee",
        "title": "刷单返利",
        "evidence": "工作内容：在家用手机给商家刷单，完成任务立返佣金",
        "context": "工作内容：在家用手机给商家刷单，完成任务立返佣金",
        "reason": "刷单本身就是违法的，而且这是最常见的诈骗入口。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-SHABU-01"
      },
      {
        "level": "red",
        "dimension": "fee",
        "title": "垫付货款返利",
        "evidence": "流程：加客服微信领取任务单，垫付货款后截图返款",
        "context": "流程：加客服微信领取任务单，垫付货款后截图返款",
        "reason": "先垫钱做任务再返款，是刷单诈骗的标准动作。",
        "source": "pattern",
        "pattern_id": "P-FEE-05",
        "rule_id": null
      },
      {
        "level": "red",
        "dimension": "fee",
        "title": "要你先垫钱",
        "evidence": "首次垫付 100 元，返 130 元，当天到账",
        "context": "首次垫付 100 元，返 130 元，当天到账",
        "reason": "让你先垫钱做任务再返，钱基本要不回来。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-ADVANCE-01"
      }
    ],
    "questions_to_ask": [
      "做任务需要我先垫钱吗？垫多少？",
      "需要我下载哪个 App？进哪个群？为什么不在平台里沟通？",
      "这个岗位要不要做刷单、点赞返利这类任务？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「薪资待遇」，可以问 HR：底薪是多少？提成怎么算？"
    ],
    "how_to_verify": [
      "任何「先垫钱再返利」的一律拒绝，这是典型套路",
      "不在官方应用商店的 App 一律不装",
      "招聘只在该平台上沟通",
      "凡是让你刷单、点赞返利的，一律不做，也别垫钱"
    ],
    "rules_version": "v3.0",
    "pattern_db_version": "2026-10-30",
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
        "level": "amber",
        "dimension": "pay",
        "title": "薪资写得糊",
        "evidence": "底薪 2500 元 + 高提成，综合薪资 8000 以上",
        "context": "底薪 2500 元 + 高提成，综合薪资 8000 以上",
        "reason": "只写「综合薪资」「按国家规定」，实际到手可能差很多。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-VAGUE-01"
      },
      {
        "level": "green",
        "dimension": "company",
        "title": "公司写得全",
        "evidence": "公司地址：高新区创业大厦 9 楼",
        "context": "公司地址：高新区创业大厦 9 楼",
        "reason": "写了公司全称或地址，可以自己核实一下。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-GREEN-COMPANY-01"
      }
    ],
    "questions_to_ask": [
      "综合薪资里底薪占多少？五险一金怎么算？",
      "（绿灯，不必提问）",
      "截图里没提到「收费与借贷」，可以问 HR：入职前需要我先交任何费用吗？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「合同社保」，可以问 HR：试用期多久？合同签几年？社保从哪个月开始缴？"
    ],
    "how_to_verify": [
      "要求把薪资结构、社保、发薪日写进书面 offer",
      "到「国家企业信用信息公示系统」搜这个全称，核对经营范围",
      "面试时把底薪、提成、发薪日再确认一遍并写进 offer"
    ],
    "rules_version": "v3.0",
    "pattern_db_version": "2026-10-30",
    "report_id": "SAMPLE-AMBER"
  },
  "green": {
    "is_job_posting": true,
    "overall": "green",
    "summary": "截图里没看到明显风险",
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
        "evidence": "公司名称：青岛示例信息技术有限公司",
        "context": "公司名称：青岛示例信息技术有限公司",
        "reason": "写了公司全称或地址，可以自己核实一下。",
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
        "reason": "薪资写得比较具体，这一项看着是清楚的。",
        "source": "rule",
        "pattern_id": null,
        "rule_id": "R-GREEN-PAY-01"
      }
    ],
    "questions_to_ask": [
      "（绿灯，不必提问）",
      "截图里没提到「收费与借贷」，可以问 HR：入职前需要我先交任何费用吗？",
      "截图里没提到「工作内容」，可以问 HR：这个岗位每天具体做什么？有没有业绩考核？",
      "截图里没提到「岗位名称」，可以问 HR：岗位名称和实际职责一致吗？",
      "截图里没提到「合同社保」，可以问 HR：试用期多久？合同签几年？社保从哪个月开始缴？"
    ],
    "how_to_verify": [
      "到「国家企业信用信息公示系统」搜这个全称，核对经营范围",
      "面试时把底薪、提成、发薪日再确认一遍并写进 offer"
    ],
    "rules_version": "v3.0",
    "pattern_db_version": "2026-10-30",
    "report_id": "SAMPLE-GREEN"
  },
  "unknown": {
    "is_job_posting": true,
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
      "这个岗位的日常工作内容是什么？",
      "工资结构和发薪时间怎么安排？"
    ],
    "how_to_verify": [
      "到国家企业信用信息公示系统核对公司信息",
      "面试地点选在公司办公场所，不去酒店或私人住所"
    ],
    "rules_version": "v3.0",
    "pattern_db_version": "2026-10-30",
    "report_id": "SAMPLE-UNKNOWN"
  }
};

export function getExampleReport(overall) {
  return EXAMPLE_REPORTS[overall] || null;
}
