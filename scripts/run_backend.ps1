# 起本地后端服务（B 关口联调用）
# 用法：scripts\run_backend.ps1 [-Port 8000]
param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = $env:PYTHON
if (-not $py) {
    $candidate = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $candidate) { $py = $candidate } else { $py = "python" }
}

if (-not $env:QBL_DB_PATH) { $env:QBL_DB_PATH = Join-Path $root "var\backend\qbl.db" }
# 开发登录通道（code=mock）：只在本机联调脚本里打开，生产部署不要设这个变量
if (-not $env:QBL_DEV_MODE) { $env:QBL_DEV_MODE = "1" }

Write-Host "后端启动：http://127.0.0.1:$Port   （接口文档 /docs）"
Write-Host "数据库：$env:QBL_DB_PATH"
Write-Host "开发登录：QBL_DEV_MODE=$env:QBL_DEV_MODE（code=mock 可直接换 token）"
& $py -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
