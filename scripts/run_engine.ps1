# 一键跑引擎：给一张 OCR 文本，出一份报告
# 用法：
#   scripts\run_engine.ps1 -OcrText data\testset\ocr\T001.txt [-Out var\smoke\T001.json] [-Model mock]
param(
    [Parameter(Mandatory = $true)][string]$OcrText,
    [string]$Out = "var\smoke\report.json",
    [string]$TraceOut = "",
    [string]$Model = "mock",
    [switch]$NoDedupe
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = $env:PYTHON
if (-not $py) {
    $candidate = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $candidate) { $py = $candidate } else { $py = "python" }
}

$argsList = @("-m", "engine.cli", "analyze", "--ocr-text", $OcrText, "--out", $Out, "--model", $Model)
if ($TraceOut) { $argsList += @("--trace-out", $TraceOut) }
if ($NoDedupe) { $argsList += "--no-dedupe" }

& $py @argsList
exit $LASTEXITCODE
