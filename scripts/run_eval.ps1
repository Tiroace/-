# 一键评测：跑 20 条测试集，输出 §4.5 四项指标
# 用法：
#   scripts\run_eval.ps1                     # 正式（Mock 注入缺陷）
#   scripts\run_eval.ps1 -Compare data\eval\eval_report.json   # 回归比对
#   scripts\run_eval.ps1 -NoMockDefects      # 对照组
param(
    [string]$Out = "data\eval\eval_report.json",
    [string]$Compare = "",
    [switch]$NoMockDefects,
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = $env:PYTHON
if (-not $py) {
    $candidate = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $candidate) { $py = $candidate } else { $py = "python" }
}

$argsList = @("-m", "engine.evaluate", "--out", $Out)
if ($Compare) { $argsList += @("--compare", $Compare) }
if ($NoMockDefects) { $argsList += "--no-mock-defects" }
if ($Limit -gt 0) { $argsList += @("--limit", "$Limit") }

& $py @argsList
exit $LASTEXITCODE
