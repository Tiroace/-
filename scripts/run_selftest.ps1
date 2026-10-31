# 一键自测：37 项功能自测（词库/证据/校准/schema/注入/脱敏/去重/全链路）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = $env:PYTHON
if (-not $py) {
    $candidate = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $candidate) { $py = $candidate } else { $py = "python" }
}

& $py -m engine.selftest
exit $LASTEXITCODE
