# IDE 自动化操作手册（软件测试者负责）

- 生效：2026-11-03，按 Chief 分工调整——`cli.bat open` / `cli.bat auto` 由**软件测试者**操作，前端开发者只做本地构建。
- 为什么改：两个人抢 9420/9422 会互相打断，更严重的是会打断老板扫码。
- 本文件与 `docs/01-环境与工具链.md` §2 互补：那边讲环境，这边讲**谁在什么时候怎么用**。

## 一、谁可以动 IDE

| 角色 | 可以做什么 | 不可以做什么 |
| --- | --- | --- |
| 软件测试者 | `cli.bat open` / `auto` / `quit`，跑自动化脚本、截图 | — |
| 前端开发者 | 本地构建（`cd src && pnpm build:mp-weixin`） | 不碰 `cli.bat open/auto`，不动 9420/9422 |
| 其他人 | 只读 `dist/build/mp-weixin` 产物 | 同上 |

`miniprogram/scripts/open_wechat_ide.ps1` 仍归前端维护，但**要不要调用、什么时候调用以测试者为准**。

## 二、标准流程（提审截图 / 自动化走查）

```powershell
# 0) 先看别人有没有在跑，避免抢端口
Get-NetTCPConnection -LocalPort 9420,9422 -ErrorAction SilentlyContinue

# 1) 拉起自动化通道（游客 appid 就够，不用真实 AppID）
cd D:\qiuzhibilei
& "D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" auto `
    --project "D:\qiuzhibilei\src\dist\build\mp-weixin" `
    --port 9420 --auto-port 9422

# 2) 通道自检（必做，别等脚本跑挂了才发现）
cd tests
node ide-probe.mjs

# 3) 跑具体任务（截图 / 走查）
node ../src/scripts/shot-pages.mjs

# 4) 用完断开，把端口让出来
& "D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" quit
```

**第 2 步不能省**：`cli.bat auto` 打印 `√ auto` 只代表命令被接受，不代表 automator 真能连上、更不代表能读到渲染文本。`ide-probe.mjs` 会真连一次、读一次当前页文本，读不到任何文本就 `exit 1`。

## 三、踩过的坑（每条都是实测）

### 1. 端口被别的进程占着
`cli.bat` 报 `IDE may already started at port 9420`。
**来源**：前端开发者 2026-10-31 观测到一次是 Tabbit 浏览器占了 64750 导致 IDE 抢不到（**该现象本人未复现**，写入时 64750 已无人占用）。仅作线索参考，遇到时按下面的通用解法处理。
解法：先 `cli.bat quit`，必要时 `taskkill /F /IM "微信开发者工具.exe" /T`，再重新 `auto`。端口被占时先查占用者：`Get-NetTCPConnection -LocalPort <端口> | Select OwningProcess`。

### 2. `page.data()` / `$vm.$el` 读不到数据
uni-app 的 `ref` 在运行时会解包，automator 的 `page.data()` 拿到的全是 `undefined`；`$vm.$el` 存在但是空的。
**解法：用 `page.$$('view')` 读渲染层文本**，逐个 `node.text()`。这反而更可信——读到的就是用户看到的。

### 3. `open`/`preview`/`upload` 要真实 AppID
只有 `auto` 接受游客 `touristappid`。要出预览码/上传时走
`reports/真机预览重出码标准动作.md`：注入真实 appid → 执行 → 恢复占位符，AppID 只留在环境变量里。

### 4. 截图内容合规
首页截图必须先滚回顶部再截，否则主视觉区和「示例报告」入口会被截掉，提审不合格。
红报告页才有 12333 文字行（`v-if="overall === 'red'"`），黄/绿/未知页校验时不该要求它。

## 四、自检脚本

| 脚本 | 作用 |
| --- | --- |
| `tests/ide-probe.mjs` | 通道自检：连 9422 → 读当前页 → 打印节点数/字数/样本；不通或读不到文本即 `exit 1` |
| `src/scripts/shot-pages.mjs` | 提审截图 |
| `src/scripts/shot-examples.mjs` | 示例报告截图 |

`ide-probe.mjs` 支持 `QBL_AUTO_PORT` 覆盖端口，`--json` 输出结构化结果，方便接进 CI 或别的脚本。
