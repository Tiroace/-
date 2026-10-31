# 一键全量测试：用 DSH 自带 Python 跑 pytest（依赖都在里面）
# 注意：PATH 里的 python 可能是本机其它软件自带的（本机是 D:\KiCad\bin\python.exe，没有 pytest）
# 用法：scripts\run_pytest.ps1            # pytest tests -q
#       scripts\run_pytest.ps1 -k smoke   # 透传参数
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThru
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = $env:PYTHON
if (-not $py) {
    $candidate = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $candidate) { $py = $candidate } else { $py = "python" }
}

& $py -m pytest tests -q @PassThru
exit $LASTEXITCODE
