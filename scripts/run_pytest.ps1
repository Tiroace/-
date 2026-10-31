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

# 无参数：全量；首个参数以 '-' 开头：在 tests 目录上加过滤；否则把参数当 pytest 目标（文件/节点）传
if ($PassThru.Count -eq 0) {
    $targets = @("tests", "-q")
} elseif ($PassThru[0].StartsWith("-")) {
    $targets = @("tests") + $PassThru
} else {
    $targets = $PassThru
}

& $py -m pytest @targets
exit $LASTEXITCODE
