# 附录 B · 自动化断言最终结果（12/12 全过）

- 执行时间：2026-10-31 14:22
- 环境：微信开发者工具 **2.02.2608080**（从 2.01 升级而来）
- 工程：`miniprogram/dist/build/mp-weixin`（正式包，9 页，无 dev 页）
- 自动化端口：`ws://127.0.0.1:9422`（IDE HTTP 端口 64750，`.ide-status=On`）
- 命令：`node tests/support/e1-assertions.js ws://127.0.0.1:9422`

## 一、结果总览：**12 / 12 通过**

| # | 断言 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 首页主界面：大标题 / 主按钮 / 剩余次数 / 不扣次数承诺 | ✅ | 4 项齐备 |
| 2 | 示例报告入口 + 红黄绿三色信号灯说明 | ✅ | 齐备 |
| 3 | 首页 AI 服务公示（派书 §3） | ✅ | 「本服务由 AI 生成内容，查看 AI 服务说明」 |
| 4 | 报告页可达 | ✅ | route=pages/report/index |
| 5 | 报告页 AI 标识 + 免责声明 | ✅ | 均在 |
| 6a | 报告页「判断不准？告诉我们」 | ✅ | 存在 |
| 6b | 我的页「意见反馈与申诉」 | ✅ | 存在 |
| 7 | 会员页可达 + 到期不自动续费 | ✅ | 声明齐备 |
| 8 | 我的页隐私政策 + 用户协议入口 | ✅ | 均在 |
| 9 | 分析中页分段阶段文案 | ✅ | 命中 4/4 |
| 10 | 连续页面跳转稳定性（5 次） | ✅ | index → member → mine → analyzing → index |
| 11 | 首页截图取证 | ✅ | `reports/e1-simulator.png`（67,027 bytes） |

**截图已人工确认**：深色主题正常渲染，含品牌标识「面试请等等」、大标题「去面试之前，先让我看一眼」、
黄色主按钮「选截图，开始检查」、「还能免费查 3 次 / 没查出结果，不扣次数」、示例报告入口、
「每份报告，逐项给你亮灯」、底部三 tab（检查 / 广场 / 我的）。

## 二、按 Chief 定性做的三处修正

| 原问题 | Chief 定性 | 我的处理 |
| --- | --- | --- |
| #1、#2 首页断言失败 | 断言过时：改版后文案变了 | 按真实文案重写：主按钮「选截图，开始检查」、示例入口「没有截图？先看一份示例报告」、风险表达改为红/黄/绿灯 |
| #3 首页 AI 公示缺失 | **真缺口**，已派前端补 | 前端 14:18 构建补上「本服务由 AI 生成内容，查看 AI 服务说明」，断言转绿 |
| #6 报告页申诉入口 | 断言过严：申诉在「我的」页 | 拆成 **6a 报告页判断不准** + **6b 我的页申诉**两条分别断言 |

## 三、我在复跑中额外发现并处理的两个工具层问题

### L9：IDE 2.02 的 automator 元数据接口失效
- **现象**：`reLaunch` 后 `mp.evaluate(() => getCurrentPages())` 报
  `Cannot destructure property 'rawPath' of 't.getPageMetaByWebviewId(...)' as it is null`
- **影响**：之前「读页面 data 再断言文案」的写法整体失效
- **处理**：**文案断言全部改为读编译产物**（`pages/<p>/*.wxml` 与 `*.js`），
  运行时只断言「路由可达 + 截图」。两者分离后，**工具缺陷不会污染产品结论**。

### L10：截图必须放在连续跳转之前
- **现象**：连跳 4–5 次页面后再截图，报 `timeout waiting for automator response`
- **实测**：单独截图 **1289 ms** 成功；放最后则超时
- **处理**：把截图断言调到连续跳转**之前**执行，并放宽超时到 30s。调整后稳定通过。

> 这两条都是**工具/使用方式**问题，不是产品缺陷。写在这里是为了后来人不再重复排查。

## 四、对上线清单的影响

- **A5（自动化验收）：可以转绿** —— 断言 12/12、截图已出且人工确认渲染正常。
- 仍需注意：本次断言主要覆盖**文案与可达性**；**真实相册选图、真实广告播放、
  真实支付拉起**仍需真机，模拟器做不到。

## 五、复跑方法（给后来人）

```powershell
# 1. 确认 IDE 在跑且服务端口为 On
$ud = (Get-ChildItem "$env:LOCALAPPDATA\*\User Data\*\Default" -Directory |
       Where-Object { Test-Path (Join-Path $_.FullName '.ide-status') } | Select-Object -First 1).FullName
Get-Content (Join-Path $ud '.ide-status')    # 期望 On

# 2. 起自动化端口（若 9422 未监听）
cd "D:\Program Files (x86)\Tencent\微信web开发者工具"
cli.bat auto --project D:\qiuzhibilei\miniprogram\dist\build\mp-weixin --auto-port 9422

# 3. 跑断言
cd D:\qiuzhibilei\tests
node support\e1-assertions.js ws://127.0.0.1:9422

# 结果：reports/.e1-result.json + reports/e1-simulator.png
```

## 六、纪律提醒

用 `uni build -p mp-weixin` **直接构建**会把 `pages/dev` 打回包里（D-05 复发）。
**只能用 `pnpm build:mp-weixin`**，构建尾部会自动跑 `strip-dev-build.mjs` 清理并自检。
