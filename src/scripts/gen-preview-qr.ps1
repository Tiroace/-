<#
.SYNOPSIS
    用测试号 AppID 生成「真机预览」二维码。

.DESCRIPTION
    游客模式 touristappid 不能真机预览（CLI 会报「不存在此 AppID (code 10)」）。
    必须用测试号或正式 AppID。流程（官方文档已核实）：

      1. 浏览器打开测试号申请页，用微信扫码 → 直接分配 appid
         https://mp.weixin.qq.com/wxamp/sandbox?doc=1
      2. 把拿到的 appid 填进本脚本，或直接改 src/project.config.json 的 appid
      3. 运行本脚本 → 生成二维码图片 → 手机微信扫码

.PARAMETER AppId
    测试号或正式小程序 appid。不传则用 src/project.config.json 里现有的。

.PARAMETER SkipBuild
    跳过重新构建（产物已经是新的时用）。

.EXAMPLE
    .\src\scripts\gen-preview-qr.ps1 -AppId wx1234567890abcdef

.NOTES
    测试号能测：首页、上传截图、报告、我的、会员页展示
    测试号不能测：真实支付、激励视频广告（需要正式商户号和广告位）
#>
param(
    [string]$AppId = '',
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

$Root = 'D:\qiuzhibilei'
$MiniDir = Join-Path $Root 'src'
$SrcProjectConfig = Join-Path $MiniDir 'src\project.config.json'
$DistDir = Join-Path $MiniDir 'dist\build\mp-weixin'
$QrOut = Join-Path $Root 'reports\真机预览二维码.png'
$Cli = 'D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat'
$IdePort = 64750

$Node = 'C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
$Pnpm = 'C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs'
$UniCli = Join-Path $MiniDir 'node_modules\@dcloudio\vite-plugin-uni\bin\uni.js'

Write-Host '=== 生成真机预览二维码 ===' -ForegroundColor Cyan

# Windows PowerShell 5.1 默认按 ANSI 读文件，中文会乱码导致 JSON 解析失败，统一用 ReadAllText 指定 UTF-8
function Read-JsonUtf8($path) {
    $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
    return $text | ConvertFrom-Json
}

function Write-JsonUtf8($path, $obj) {
    $json = $obj | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# ---- 1. 确定 AppID ----
if (-not $AppId) {
    $cfg = Read-JsonUtf8 $SrcProjectConfig
    $AppId = $cfg.appid
}
if (-not $AppId -or $AppId -eq 'touristappid') {
    Write-Host ''
    Write-Host '[停在这里] 现在用的是游客模式 touristappid，不能真机预览。' -ForegroundColor Yellow
    Write-Host '官方文档已核实：测试号是在网页上申请，不需要额外认证。' -ForegroundColor Gray
    Write-Host ''
    Write-Host '要做的事（3 步）：' -ForegroundColor White
    Write-Host '  1) 浏览器打开：https://mp.weixin.qq.com/wxamp/sandbox?doc=1' -ForegroundColor Green
    Write-Host '  2) 用微信扫码登录，页面会直接给你一个 appid（小程序测试号）' -ForegroundColor Green
    Write-Host '  3) 拿到 appid 后运行：' -ForegroundColor Green
    Write-Host ''
    Write-Host ('     ' + $MyInvocation.MyCommand.Path + ' -AppId 你的appid') -ForegroundColor White
    Write-Host ''
    exit 1
}
Write-Host ('使用 AppID: ' + $AppId)

# ---- 2. 写进工程配置 ----
$cfg = Read-JsonUtf8 $SrcProjectConfig
if ($cfg.appid -ne $AppId) {
    $cfg.appid = $AppId
    Write-JsonUtf8 $SrcProjectConfig $cfg
    Write-Host '已更新 src\project.config.json 的 appid'
}

# ---- 3. 构建 ----
if (-not $SkipBuild) {
    Write-Host '[构建] pnpm build:mp-weixin ...'
    Push-Location $MiniDir
    try {
        & $Node $Pnpm build:mp-weixin
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[错误] 构建失败' -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
}

# ---- 4. 确认产物 ----
if (-not (Test-Path (Join-Path $DistDir 'app.json'))) {
    Write-Host ('[错误] 产物不存在：' + $DistDir) -ForegroundColor Red
    exit 1
}
$distCfg = Read-JsonUtf8 (Join-Path $DistDir 'project.config.json')
Write-Host ('产物里的 appid: ' + $distCfg.appid)

# ---- 5. 生成二维码 ----
Write-Host '[出码] 调用 CLI preview ...'
Remove-Item $QrOut -Force -ErrorAction SilentlyContinue
& $Cli preview --project $DistDir --port $IdePort --qr-output $QrOut --qr-format image

if (Test-Path $QrOut) {
    Write-Host ''
    Write-Host ('✓ 二维码已生成：' + $QrOut) -ForegroundColor Green
    Write-Host '  用手机微信扫这张图 → 就能在真机上打开小程序' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host '[未能出码] 常见原因：' -ForegroundColor Yellow
    Write-Host '  · IDE 没开或服务端口没开：先在 IDE 里「设置 → 安全设置 → 服务端口」打开' -ForegroundColor Yellow
    Write-Host '  · appid 不对或没有真机预览权限（测试号可以）' -ForegroundColor Yellow
    Write-Host '  · 换个方式：在 IDE 里点工具栏「预览」按钮，扫码也能上手机' -ForegroundColor Yellow
    exit 1
}
