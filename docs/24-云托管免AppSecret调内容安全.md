# 微信云托管能否免 AppSecret 调内容安全（调研结论）

**结论：能免 AppSecret，但有两个前置条件；不满足就会报 `API unauthorized`。**

**调研时间**：2026-11-03　**依据**：微信官方文档原文（已逐段核对，非凭印象）

## 一、官方原文要点

来源：[云调用&微信令牌](https://developers.weixin.qq.com/miniprogram/dev/wxcloudservice/wxcloudrun/src/guide/weixin/token.html)

1. **云调用 = 免鉴权调微信开放接口**。原文：「免鉴权，也就是**免密钥**，全程不暴漏任何信息，**开发者无需维护 access_token**」。
2. **云开发的云调用在云托管走不通**。原文：「云托管的开发语言和框架都不限定……所以云开发的云调用实现方法在云托管无法走通。云托管根据自身特点优势，推出云调用彻底免鉴权解决方案——**开放接口服务**」。
   → 不能用 `wx-server-sdk` 那套，要用云托管自己的**微信令牌**。
3. **令牌由微信后台推送到容器**：挂载路径 `/.tencentcloudbase/wx/cloudbase_access_token`；
   推送间隔 10 分钟，有效期 30 分钟；同环境所有实例令牌相同。
4. **调用方式**：令牌放在 **`cloudbase_access_token`** 参数上（不是 `access_token`）：
   ```
   POST https://api.weixin.qq.com/wxa/msg_sec_check?cloudbase_access_token=<TOKEN>
   ```
5. **必须先配白名单**。原文：「不在白名单中的接口不允许使用微信令牌」。配置位置：
   **微信云托管控制台 → 云调用 / 微信令牌配置**，填接口路径（`api.weixin.qq.com` 之后、`?` 之前的部分）：
   - 文本：`/wxa/msg_sec_check`
   - 图片：`/wxa/media_check_async`
   配置是**环境维度**的，不同环境各配各的。
6. 资源复用/服务商场景要拼 `appid@token`；本项目单主体，不需要。

## 二、对本项目的结论

| 问题 | 答案 |
| --- | --- |
| 能不能免 AppSecret？ | **能**，前提是服务部署在微信云托管（本地/别的云没有令牌文件） |
| 还要不要老板给 AppSecret？ | **内容安全这条不用**。AppSecret 只在「不走云托管」或调用未进白名单的接口时才需要 |
| 要在控制台做什么？ | 把 `/wxa/msg_sec_check` 和 `/wxa/media_check_async` 加进**该环境**的云调用白名单 |
| 图片检测能直接用吗？ | 接口本身支持，但 `mediaCheckAsync` 是**异步**的（只回 trace_id），且需要**公网可访问的图片 URL**；当前先不启用，代码里明确标 degraded，不假装已检 |

## 三、代码已实现

新增 `engine/adapters/cloudbase_safety.py`：

- `read_cloudbase_token()`：从官方挂载路径读令牌，读不到返回空串（本地开发正常情况）
- `CloudbaseTokenSafety.check_text()`：用 `cloudbase_access_token` 调 `msgSecCheck`，
  返回 `suggest=pass/review/risky`；
  - 读不到令牌 → **降级放行 + 原因**（不阻塞用户）
  - `48001/API unauthorized` → 提示「确认控制台已把接口加进白名单」
  - `40001/40014/42001` → 提示令牌无效/过期
  - 任何异常 → 降级放行，**保证不抛**

`content_safety_factory` 新增 `auto` / `cloudbase` 模式：
- `auto`（建议）：云托管里有令牌就用免鉴权，没有就用本地桩
- `cloudbase`：强制云调用（读不到令牌也降级，不偷偷换别的实现）

## 四、验证

```
pytest backend/tests                    58 passed
  └ test_cloudbase_token_safety.py      8 条（令牌参数名、risky 拦截、白名单提示、降级不抛）
  └ test_gate2_safety_bypass.py        11 条（生产拒 ocr_text、降级语义）
engine.selftest                         76/76
eval_negatives                          15/15
```

**没验证到的**：真实令牌 + 真实白名单下的端到端调用。这必须在云托管环境里跑，
本地没有令牌文件，我不会拿假结果充当验证。

## 五、给运维/老板的动作

1. 云托管开通后，控制台 → **云调用 / 微信令牌配置**，加两条：`/wxa/msg_sec_check`、`/wxa/media_check_async`
2. 部署时设 `QBL_CONTENT_SAFETY=auto`（或 `cloudbase` 强制）
3. **AppSecret 可以先不给**——内容安全这条用不上；后面订阅消息、支付等接口再看是否也需要白名单
