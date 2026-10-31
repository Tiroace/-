# wxdev-cli.ps1 - WeChat DevTools CLI wrapper for automated testing.
#
# NOTE: keep this file ASCII-only. PowerShell 5.1 reads .ps1 as GBK on this box,
# so UTF-8 Chinese comments get mangled and can break the parser.
#
# Findings that this wrapper encodes (see reports/E1-*.md):
#   1) cli.bat is `node.exe cli.js %*`. %* is flattened by cmd, so any path with
#      spaces breaks. Pass 8.3 short paths for --project (Get-ShortPath).
#   2) cmd /c "C:\Program Files\...\cli.bat" is unreliable here -> run cmd with
#      cwd = install dir and call the relative name `cli.bat`.
#   3) When the IDE service port is off, CLI blocks on an interactive
#      `Enable IDE Service (y/N)` prompt -> feed stdin 'y' and wait long enough.
#   4) An interrupted call can leave node.exe holding the CLI callback port 3800;
#      call Clean-CliLeftover before each scenario.
#
# Usage:
#   . D:\qiuzhibilei\tests\support\wxdev-cli.ps1
#   Clean-CliLeftover
#   Invoke-WxCli -ArgLine 'islogin' -TimeoutSec 90 | Show-WxCliResult

$ErrorActionPreference = 'Stop'

$script:WxInstallDir = $null
foreach ($d in (Get-ChildItem 'D:\Program Files (x86)\Tencent' -Directory)) {
    if (Test-Path (Join-Path $d.FullName 'cli.bat')) { $script:WxInstallDir = $d.FullName; break }
}
if (-not $script:WxInstallDir) { throw 'WeChat DevTools install dir (cli.bat) not found' }
$script:WxCliBat = Join-Path $script:WxInstallDir 'cli.bat'
$script:WxDevtoolsExe = Join-Path $script:WxInstallDir 'wechatdevtools.exe'
$script:WxNodeExe = Join-Path $script:WxInstallDir 'node.exe'

function Get-ShortPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fso = New-Object -ComObject Scripting.FileSystemObject
    return $fso.GetFolder($Path).ShortPath
}

# Kill only leftover `node.exe ... cli\index.js` processes, never the IDE itself.
function Clean-CliLeftover {
    $left = @(Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'cli\\index\.js' })
    $killed = @()
    foreach ($p in $left) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; $killed += $p.ProcessId } catch { }
    }
    return $killed
}

function Invoke-WxCli {
    param(
        [Parameter(Mandatory = $true)][string]$ArgLine,
        [int]$TimeoutSec = 90,
        [string]$StdinText = 'y'
    )
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $env:ComSpec
    $psi.WorkingDirectory = $script:WxInstallDir
    $psi.Arguments = "/c cli.bat $ArgLine"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [Text.Encoding]::UTF8

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = [Diagnostics.Process]::Start($psi)
    $o = $p.StandardOutput.ReadToEndAsync()
    $e = $p.StandardError.ReadToEndAsync()
    if ($StdinText) { try { $p.StandardInput.WriteLine($StdinText); $p.StandardInput.Flush() } catch { } }

    $timed = $false
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        $timed = $true
        try { $p.Kill($true) } catch { }
    }
    $sw.Stop()
    [pscustomobject]@{
        Args    = $ArgLine
        Exit    = $p.ExitCode
        Timeout = $timed
        Sec     = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        Out     = $o.Result
        Err     = $e.Result
    }
}

function Show-WxCliResult {
    param([Parameter(Mandatory = $true)]$R, [string]$Title = '')
    if ($Title) { Write-Output "===== $Title =====" }
    Write-Output ("args     : {0}" -f $R.Args)
    Write-Output ("exit     : {0}   timeout: {1}   elapsed: {2}s" -f $R.Exit, $R.Timeout, $R.Sec)
    Write-Output '--- stdout ---'
    Write-Output $R.Out
    Write-Output '--- stderr ---'
    Write-Output $R.Err
}

# Returns a string: the PID listening on $Port, or '' when nobody listens.
function Get-PortOwner {
    param([int]$Port)
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $c) { return '' }
    return ($c | Select-Object -First 1).OwningProcess
}
