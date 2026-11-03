# 环境缺陷 · 微信开发者工具 `cli.bat quit` 假成功、端口不释放

| 项 | 内容 |
|---|---|
| **类型** | 环境/工具缺陷（非产品缺陷） |
| **记录人** | 软件测试者 |
| **日期** | 2026-11-03 |
| **严重级别** | 中（阻断自动化截图，但不影响交付物） |
| **状态** | 已知问题，已绕过 |

---

## 一、现象

`cli.bat quit` **返回 `√ quit` 成功**，但：

- 微信开发者工具**后台进程不退出**（实测一次残留 **26 个进程**）；
- **9420 端口仍被原进程占用**（实测 PID 2612 持续占用）；
- 下一次 `cli.bat open --port 9420` 会报：
  ```
  × IDE may already started at port 9420, trying to connect
  × initialize error: wait IDE port timeout, undefined
  ```
- `cli.bat auto --auto-port 9422` 报 `√ auto` 成功，但 **9422 根本不监听** → 自动化端口不可用 → 截图脚本全部超时。

## 二、影响

- IDE 自动化截图链路**在 quit 之后无法恢复**；
- 表现为「命令都说成功，实际什么都没发生」，**极易误判为脚本问题**（本次就排查了很久）。

## 三、绕过方法（已采用）

**截图改走真机人工**：`cli.bat preview` 出码 → 老板在真机上按对照表截图。
真机画面本来就是提审要的画面，比模拟器更合适。

参考：`reports/真机截图-14行对照表-给老板.md`

## 四、后续任何人重启 IDE 前必做

```powershell
# 1) 先查 9420 是谁占着
Get-NetTCPConnection -LocalPort 9420 -State Listen | Select-Object LocalPort,OwningProcess

# 2) 查 IDE 全部进程
Get-Process | Where-Object { $_.ProcessName -match '微信开发者工具|WeChatAppEx' } |
  Select-Object Id,ProcessName,StartTime

# 3) 手动结束（quit 不可信，必须强杀）
Get-Process | Where-Object { $_.ProcessName -match '微信开发者工具|WeChatAppEx' } |
  ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} }

# 4) 确认端口已释放（应为空）
Get-NetTCPConnection -LocalPort 9420 -State Listen -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 9422 -State Listen -ErrorAction SilentlyContinue

# 5) 再拉起
cd "D:\Program Files (x86)\Tencent\微信web开发者工具"
cli.bat open --project <8.3短路径> --port 9420
```

## 五、经验

1. **`√ quit` 不等于进程退出**，必须用端口是否释放来判定；
2. 判定顺序永远是：**先看端口，再看进程，最后才怀疑脚本**；
3. 强杀后 IDE 可能起不来「主窗口」只有子进程 —— 需要等更久或直接启动图形界面恢复；
4. 自动化端口 9422 起不来时，本轮**放弃自动化，改人工**，不要反复试同一命令。

## 六、附带说明

`appid` 注入与恢复流程本身没问题（`wx-preview-qr.ps1` 已验证：注入无 BOM、出码成功、自动恢复占位符、全仓明文 0 命中），**卡住的只是 IDE 进程/端口状态**。
