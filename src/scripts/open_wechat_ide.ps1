<#
.SYNOPSIS
    用固定端口 9420 打开微信开发者工具，指向小程序编译产物目录。

.DESCRIPTION
    为什么要有这个脚本：
    1. IDE 必须以 CLI 带 --port 启动，HTTP 服务端口才会固定成 9420；
       用普通方式双击启动会分配到随机端口，自动化（miniprogram-automator）就连不上。
    2. 工程目录必须是「编译产物目录」dist\build\mp-weixin（里面有 app.json），
       不是仓库根 D:\qiuzhibilei，否则模拟器会报「在项目根目录未找到 app.json」。

.PARAMETER Restart
    先 cli.bat quit 关掉现有 IDE 再开。不加这个参数就只是 open（IDE 已开时会切到该项目）。

.PARAMETER Build
    打开前先跑一次 mp-weixin 构建。

.EXAMPLE
    .\src\scripts\open_wechat_ide.ps1
    .\src\scripts\open_wechat_ide.ps1 -Restart -Build
#>
param(
    [switch]$Restart,
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

# ---- 固定路径（改这里即可，不要散落在各处） ----
$ProjectRoot = 'D:\qiuzhibilei'
$MiniprogramDir = Join-Path $ProjectRoot 'src'
$DistDir = Join-Path $MiniprogramDir 'dist\build\mp-weixin'
$Cli = 'D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat'
$Port = 9420

# DSH 运行时里的 node / pnpm（本机没有独立 npm）
$Node = 'C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
$Pnpm = 'C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs'
$UniCli = Join-Path $MiniprogramDir 'node_modules\@dcloudio\vite-plugin-uni\bin\uni.js'

Write-Host '=== 打开微信开发者工具（固定端口 ' $Port '） ===' -ForegroundColor Cyan

# ---- 0. 前置检查：CLI 存不存在 ----
if (-not (Test-Path $Cli)) {
    Write-Host '[错误] 找不到微信开发者工具 CLI：' $Cli -ForegroundColor Red
    Write-Host '       请确认开发者工具安装路径，或改本脚本顶部的 $Cli。' -ForegroundColor Yellow
    exit 1
}

# ---- 1. 可选：先构建 ----
if ($Build) {
    if (-not (Test-Path $UniCli)) {
        Write-Host '[错误] 找不到 uni-app CLI，先在 miniprogram 目录装依赖：' -ForegroundColor Red
        Write-Host ('       ' + $Node + ' ' + $Pnpm + ' install') -ForegroundColor Yellow
        exit 1
    }
    Write-Host '[1/3] 正在构建 mp-weixin ...'
    Push-Location $MiniprogramDir
    try {
        & $Node $UniCli build -p mp-weixin
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[错误] 构建失败，已中止。' -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Host '      构建完成。' -ForegroundColor Green
} else {
    Write-Host '[1/3] 跳过构建（需要构建请加 -Build）'
}

# ---- 2. 检查产物目录（不存在就提示，不自动猜） ----
Write-Host '[2/3] 检查编译产物目录 ...'
$AppJson = Join-Path $DistDir 'app.json'
if (-not (Test-Path $AppJson)) {
    Write-Host ''
    Write-Host '[错误] 编译产物不存在：' $DistDir -ForegroundColor Red
    Write-Host '       请先构建，任选一种：' -ForegroundColor Yellow
    Write-Host ('         a) 本脚本自带： .\src\scripts\open_wechat_ide.ps1 -Build') -ForegroundColor Yellow
    Write-Host ('         b) 手动构建：   cd ' + $MiniprogramDir) -ForegroundColor Yellow
    Write-Host ('                         ' + $Node + ' ' + $Pnpm + ' run build:mp-weixin') -ForegroundColor Yellow
    Write-Host ('         c) 或直接：     ' + $Node + ' ' + $UniCli + ' build -p mp-weixin') -ForegroundColor Yellow
    Write-Host ''
    Write-Host '       注意：工程目录必须是 dist\build\mp-weixin，不是仓库根 D:\qiuzhibilei。' -ForegroundColor Yellow
    exit 1
}
Write-Host ('      app.json 已找到：' + $AppJson) -ForegroundColor Green

# ---- 3. 可选：重启 IDE ----
if ($Restart) {
    Write-Host '[可选] 先关闭现有 IDE ...'
    & $Cli quit
    Start-Sleep -Seconds 3
}

# ---- 4. 用固定端口打开 ----
Write-Host ('[3/3] 用 CLI 打开（端口 ' + $Port + '）...')
& $Cli open --project $DistDir --port $Port --lang zh

if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '[警告] CLI open 返回非 0。常见原因：' -ForegroundColor Yellow
    Write-Host '       1) IDE 已在运行且没开服务端口 → 加 -Restart 重开一次' -ForegroundColor Yellow
    Write-Host '       2) IDE 界面里「设置 → 安全设置 → 服务端口」没打开' -ForegroundColor Yellow
    Write-Host '       3) 端口被占用：netstat -ano | findstr ' $Port -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host ('完成：IDE 已指向 ' + $DistDir) -ForegroundColor Green
Write-Host ('HTTP 服务端口：http://127.0.0.1:' + $Port + '（自动化固定连这个）') -ForegroundColor Green
Write-Host '编译出新版本后，在 IDE 里点一下「编译」即可刷新，不用重开。' -ForegroundColor Gray
