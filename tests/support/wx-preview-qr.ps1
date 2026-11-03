# wx-preview-qr.ps1 - one-shot real-device preview QR for the Mini Program.
# ASCII only (PS 5.1 mangles BOM-less UTF-8 Chinese).
#
# Does, in order:
#   1) read AppID from $env:DSH_SECRET_WX_TEST_APPID (never printed)
#   2) inject it into the BUILD artifact project.config.json (UTF-8, NO BOM)
#   3) cli.bat preview -f image -o <jpg>   (also kills stale IDE first)
#   4) ALWAYS restore the placeholder in finally
#   5) repo-wide plaintext scan for the AppID -> must be 0 hits
#
# Usage (from D:\qiuzhibilei):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\support\wx-preview-qr.ps1
#
# NOTE (2026-11-03): default paths point at src\ (the real source root).
#   D:\qiuzhibilei\miniprogram\ is a .gitignore'd LEGACY dir - do not use it.
# NOTE on IDE: cli.bat quit lies (returns ok, processes stay, port 9420 stays held).
#   This script force-kills stale IDE processes before preview.

param(
    [string]$Project = 'D:\qiuzhibilei\src\dist\build\mp-weixin',
    [string]$SrcConfig = 'D:\qiuzhibilei\src\src\project.config.json',
    [string]$RepoRoot = 'D:\qiuzhibilei',
    [string]$OutDir = 'D:\qiuzhibilei\reports',
    [int]$TimeoutSec = 180,
    [switch]$NoKillIde
)

$ErrorActionPreference = 'Stop'
. 'D:\qiuzhibilei\tests\support\wxdev-cli.ps1'

# --- force-kill stale IDE (quit is unreliable on this box) ---
if (-not $NoKillIde) {
    $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '微信开发者工具|WeChatAppEx' })
    if ($procs.Count -gt 0) {
        Write-Output ("killing stale IDE processes: " + $procs.Count)
        foreach ($p in $procs) { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { } }
        Start-Sleep -Seconds 6
    }
    $held = @(Get-NetTCPConnection -LocalPort 9420 -State Listen -ErrorAction SilentlyContinue)
    if ($held.Count -gt 0) {
        # 注意：这里看到的占用通常是 CLI 自己刚拉起的 IDE，不是残留。
        # 只要 cli preview 能成功，这一行不用管；若随后 preview 报 wait IDE port timeout，
        # 再手动强杀一次（见 环境缺陷-微信开发者工具quit假成功.md）。
        Write-Output ("note: port 9420 currently listening (PID " + (($held | ForEach-Object { $_.OwningProcess }) -join ',') + ") - usually the IDE the CLI just spawned")
    } else {
        Write-Output 'port 9420 is free'
    }
}

$appid = $env:DSH_SECRET_WX_TEST_APPID
if (-not $appid) { throw 'DSH_SECRET_WX_TEST_APPID is not set' }

$cfg = Join-Path $Project 'project.config.json'
if (-not (Test-Path -LiteralPath $cfg)) { throw "not found: $cfg" }
if (-not (Test-Path -LiteralPath $SrcConfig)) { throw "not found: $SrcConfig" }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outFile = Join-Path $OutDir ("preview-qr-$stamp.jpg")
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$utf8NoBom = New-Object Text.UTF8Encoding($false)
$restored = $false

function Restore-Placeholder {
    $srcTxt = [IO.File]::ReadAllText($SrcConfig, [Text.Encoding]::UTF8)
    [IO.File]::WriteAllText($cfg, $srcTxt, (New-Object Text.UTF8Encoding($false)))
}

try {
    # 1) inject (no BOM)
    $srcTxt = [IO.File]::ReadAllText($SrcConfig, [Text.Encoding]::UTF8)
    $newTxt = [regex]::Replace($srcTxt, '"appid"\s*:\s*"[^"]*"', { param($m) '"appid": "' + $script:appid + '"' })
    [IO.File]::WriteAllText($cfg, $newTxt, $utf8NoBom)

    # sanity: parses and appid matches, without printing the value
    $j = [IO.File]::ReadAllText($cfg, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ($j.appid -ne $appid) { throw 'inject verification failed' }
    Write-Output 'appid injected OK'

    # 2) preview -> image
    $sp = Get-ShortPath $Project
    $argLine = 'preview --project {0} -f image -o "{1}"' -f $sp, $outFile
    $r = Invoke-WxCli -ArgLine $argLine -TimeoutSec $TimeoutSec -StdinText ''
    Write-Output ("cli exit={0} timeout={1} elapsed={2}s" -f $r.Exit, $r.Timeout, $r.Sec)
    foreach ($line in (($r.Out + "`n" + $r.Err) -split "`n")) {
        if ($line -match 'preview|AppID|error|code') {
            Write-Output ('  ' + ($line -replace [regex]::Escape($appid), '[secret]'))
        }
    }
    if ($r.Timeout) { throw 'preview timed out' }
    if (-not (Test-Path -LiteralPath $outFile)) { throw 'preview reported no error but no image was written' }
}
finally {
    Restore-Placeholder
    $restored = $true
    $j2 = [IO.File]::ReadAllText($cfg, [Text.Encoding]::UTF8) | ConvertFrom-Json
    Write-Output ("placeholder restored: {0}" -f ($j2.appid -eq 'touristappid'))
}

# 3) leak scan (repo-wide, skip node_modules/.git)
$hits = @()
Get-ChildItem $RepoRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch '\\node_modules\\|\\\.git\\' -and
        $_.Length -lt 2MB -and
        $_.Extension -match '^\.(json|js|py|md|txt|ps1|bat|cmd|env|toml|yaml|yml|html|wxml|wxss|example)$'
    } |
    ForEach-Object {
        if (Select-String -LiteralPath $_.FullName -SimpleMatch $appid -ErrorAction SilentlyContinue) { $hits += $_.FullName }
    }
Write-Output ("appid plaintext leaks: {0}" -f $hits.Count)
foreach ($h in $hits) { Write-Output ('  LEAK: ' + $h) }

if (Test-Path -LiteralPath $outFile) {
    $len = (Get-Item -LiteralPath $outFile).Length
    Write-Output ("QR IMAGE: {0} ({1} bytes)" -f $outFile, $len)
} else {
    Write-Output 'QR IMAGE: none'
}
if ($hits.Count -gt 0) { exit 2 }
exit 0
