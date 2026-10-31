"""追加真实话术到 real_phrases_v1.json（P031 起）

所有话术均逐字摘自已抓取的正文，可在 var/fetched/fetch-a2a6.json 中回查。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "testset" / "real_phrases_v1.json"

NEW = [
    # ---- A4 成都通报：招转租、非法职介、央国企就业指导 ----
    dict(id="P031", dimension="fee", level="red",
         text="通过微信视频号发布部分央国企招聘信息，并收取高额求职指导费",
         source="A4", category="付费内推", why="无资质收取求职指导费，属非法职介"),
    dict(id="P032", dimension="company", level="red",
         text="央国企就业指导、内部渠道",
         source="A4", category="虚假渠道", why="官方点名提醒：所谓内部渠道多为骗局"),
    dict(id="P033", dimension="work", level="red",
         text="以物流公司高薪招聘司机为诱饵，诱使求职者贷款租车购车",
         source="A4", category="招转租", why="以招聘为名诱导贷款买车租车"),
    dict(id="P034", dimension="pay", level="red",
         text="综合月收入9500元至13500元",
         source="A4", category="高薪诱饵", why="高薪承诺配合租车押金，是招转租典型组合"),
    dict(id="P035", dimension="fee", level="red",
         text="通过网络平台绑定自动扣款",
         source="A4", category="变相收费", why="绑卡自动扣款比收押金更隐蔽"),

    # ---- A5 官方通报：多类收费名目与骗术 ----
    dict(id="P036", dimension="fee", level="red",
         text="凡是提前收取体检费、安置费、资料费、中介费的",
         source="A5", category="前置收费（官方警示）", why="官方明确列为需警惕的收费名目"),
    dict(id="P037", dimension="company", level="red",
         text="零门槛、高薪保底、国企内推、包入职",
         source="A5", category="虚假承诺", why="官方点名的四类虚假噱头"),
    dict(id="P038", dimension="company", level="amber",
         text="超高薪资、特殊渠道招聘大概率为骗局",
         source="A5", category="警示语（反例）", why="官方提示"),
    dict(id="P039", dimension="company", level="red",
         text="冒用他人名义招聘、发布虚假岗位信息、欺诈收费牟利",
         source="A5", category="冒名招聘", why="冒名+欺诈收费组合"),
    dict(id="P040", dimension="title", level="amber",
         text="无经验骑手、月入9000元",
         source="A5", category="高薪诱饵", why="无门槛高薪"),
    dict(id="P041", dimension="fee", level="red",
         text="按每人500元的标准收取人员推荐服务费",
         source="A5", category="变相收费", why="向合作方收费并转嫁成本"),

    # ---- A6 大连公安：虚构辅警招聘 ----
    dict(id="P042", dimension="title", level="red",
         text="将某安保公司招聘保安的信息虚构为招聘公安辅警",
         source="A6", category="岗位造假", why="把保安岗包装成公安辅警，冒充公职"),
    dict(id="P043", dimension="company", level="red",
         text="3个月转正、与公安机关直签合同",
         source="A6", category="虚假承诺", why="伪造与公安机关直签的承诺"),
    dict(id="P044", dimension="fee", level="red",
         text="共有3人报名并交纳保证金共计2万元",
         source="A6", category="前置收费", why="以报名名义收保证金"),
    dict(id="P045", dimension="company", level="red",
         text="通过微信群、朋友圈发布相关虚假招聘信息",
         source="A6", category="传播渠道", why="非正规渠道发布，无法核实"),
    dict(id="P046", dimension="contract", level="amber",
         text="报考人员均需通过报名、资格审查、笔试、体能测试、心理素质测试、面试、体检、考察、公示等环节",
         source="A6", category="正规流程（反例）", why="正规公职招聘必有完整流程，可用来识别「免试直签」"),

    # ---- A3 法治网/人民日报：其余段落 ----
    dict(id="P047", dimension="contract", level="red",
         text="利用求职者急于就业的心理，以岗前培训考核、适应性试岗为名",
         source="A3", category="无薪试岗", why="利用求职焦虑设置无薪期"),
    dict(id="P048", dimension="fee", level="red",
         text="以发布招聘信息名义，向合作单位收取200元至700元不等的广告费、信息推广费",
         source="A3", category="变相收费", why="无许可证从事职业中介并收费"),
    dict(id="P049", dimension="title", level="amber",
         text="以特定户籍、特定地域、某少数民族名额已满等说辞",
         source="A3", category="就业歧视", why="以户籍民族为由的就业歧视"),
    dict(id="P050", dimension="pay", level="amber",
         text="口头承诺支付每月薪资8000元，但未签订书面劳动合同",
         source="A3", category="口头承诺", why="只口头承诺不签合同，维权无据"),
]


def main() -> int:
    data = json.loads(P.read_text(encoding="utf-8"))
    existing = {p["id"] for p in data["phrases"]}
    added = 0
    for item in NEW:
        if item["id"] in existing:
            continue
        data["phrases"].append(item)
        added += 1
    data["version"] = "v1.1"
    data["note"] = (
        "话术逐字摘自 A2/A3/A4/A5/A6 正文，可在 var/fetched/fetch-a2a6.json 回查；"
        "A1 公安部站点 521 不可达，十个陷阱话术待补"
    )
    P.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"追加 {added} 条，现共 {len(data['phrases'])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
