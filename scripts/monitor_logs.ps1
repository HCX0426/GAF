<#
.SYNOPSIS
  GAF real-time log monitor - tail backend + agent + per-execution logs with error highlight

.DESCRIPTION
  N194 归一化 + 嵌套结构 (2026-07-29): Monitors unified per-execution directory layout:

  1. <GAF_ROOT>/debug/_global/run.log                              - backend global log (WARNING+)
  2. <GAF_ROOT>/debug/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/run.log         - per-execution backend log
  3. <GAF_ROOT>/debug/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/structured.jsonl - per-execution agent structured log
  4. agent/logs/agent.log                                          - agent full log (INFO+)

  嵌套结构 (2026-07-29): <exec_dir> = <YYYYMMDD>/<safe_task_name>/<HHMMSS>_<exec_id_suffix8>
  旧扁平格式兼容 (pre-2026-07-29): <exec_dir> = <YYYYMMDD_HHMMSS>_<safe_task_name>_<exec_id_suffix8>

  Error keywords highlighted: ERROR, CRITICAL, Traceback, Exception, FAIL

  N192-A2 fix (2026-07-28): Force UTF-8 encoding for console output and
  Get-Content so backend/agent Chinese log messages (e.g. "任务已分配")
  display correctly instead of being garbled as GBK.

.USAGE
  pwsh scripts/monitor_logs.ps1                 # monitor all
  pwsh scripts/monitor_logs.ps1 -ErrorsOnly     # errors only
  pwsh scripts/monitor_logs.ps1 -AgentOnly      # agent only
  pwsh scripts/monitor_logs.ps1 -BackendOnly    # backend only
  pwsh scripts/monitor_logs.ps1 -ExecId <id>    # filter by execution_id suffix
#>
param(
    [switch]$ErrorsOnly,
    [switch]$AgentOnly,
    [switch]$BackendOnly,
    [string]$ExecId
)

$ErrorActionPreference = "Continue"

# N192-A2 fix (2026-07-28): Force UTF-8 for console + file reads so backend/agent
# Chinese log messages display correctly. Without this PowerShell defaults to
# the system OEM codepage (GBK on zh-CN Windows) and garbles UTF-8 logs.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null 2>&1

$GafRoot = Resolve-Path "$PSScriptRoot/.."
# N194 归一化: backend + agent 共享 <GAF_ROOT>/debug/ 作为归一化根目录.
# backend 本地镜像在 <GAF_ROOT>/backend/debug/, agent 本地镜像在 <agent_cwd>/debug/.
$UnifiedDebugDir = Join-Path $GafRoot "debug"
$BackendLogsDir = $UnifiedDebugDir  # 视角 B: 用户在此浏览所有执行
$AgentLog = Join-Path $GafRoot "agent/logs/agent.log"

# Ensure agent/logs directory exists
$AgentLogsDir = Split-Path $AgentLog -Parent
if (-not (Test-Path $AgentLogsDir)) {
    New-Item -ItemType Directory -Path $AgentLogsDir -Force | Out-Null
}

# Keywords to highlight (errors)
$ErrorKeywords = @(
    "ERROR", "CRITICAL", "Traceback", "Exception",
    "FAIL", "ValidationError", "KeyError", "AttributeError",
    "TypeError", "ValueError", "ImportError",
    "node.*fail", "execution.*fail", "connect.*fail"
)
$ErrorPattern = ($ErrorKeywords | ForEach-Object { [regex]::Escape($_) }) -join "|"

function Write-LogLine {
    param(
        [string]$Source,
        [string]$Line
    )

    $isError = $false
    if ($Line -match $ErrorPattern) {
        $isError = $true
    }

    if ($ErrorsOnly -and -not $isError) {
        return
    }

    $timestamp = Get-Date -Format "HH:mm:ss"
    $prefix = "[$timestamp] [$Source]"
    if ($isError) {
        Write-Host "$prefix $Line" -ForegroundColor Red
    }
    elseif ($Line -match "WARN") {
        Write-Host "$prefix $Line" -ForegroundColor Yellow
    }
    elseif ($Line -match "INFO") {
        Write-Host "$prefix $Line" -ForegroundColor Gray
    }
    else {
        Write-Host "$prefix $Line" -ForegroundColor White
    }
}

# Main
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GAF Real-time Log Monitor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Mode: $(if ($ErrorsOnly) { 'errors-only' } else { 'all' })" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to exit" -ForegroundColor Cyan
Write-Host ""

$jobs = @()

if (-not $BackendOnly) {
    # Watch agent log
    $jobs += Start-Job -ScriptBlock {
        param($path, $src, $errsOnly, $pattern)
        $ErrorActionPreference = "Continue"
        function Write-LogLine {
            param([string]$Source, [string]$Line)
            $isError = $false
            if ($Line -match $pattern) { $isError = $true }
            if ($errsOnly -and -not $isError) { return }
            $timestamp = Get-Date -Format "HH:mm:ss"
            $prefix = "[$timestamp] [$Source]"
            if ($isError) {
                Write-Host "$prefix $Line" -ForegroundColor Red
            }
            elseif ($Line -match "WARN") {
                Write-Host "$prefix $Line" -ForegroundColor Yellow
            }
            elseif ($Line -match "INFO") {
                Write-Host "$prefix $Line" -ForegroundColor Gray
            }
            else {
                Write-Host "$prefix $Line" -ForegroundColor White
            }
        }
        if (-not (Test-Path $path)) {
            Write-Host "[monitor] waiting for $src log file: $path" -ForegroundColor Cyan
            while (-not (Test-Path $path)) { Start-Sleep -Seconds 1 }
        }
        Write-Host "[monitor] tailing $src : $path" -ForegroundColor Green
        Get-Content $path -Tail 20 -Encoding UTF8 | ForEach-Object { Write-LogLine -Source $src -Line $_ }
        Get-Content $path -Wait -Encoding UTF8 | ForEach-Object {
            if ($_ -ne "") { Write-LogLine -Source $src -Line $_ }
        }
    } -ArgumentList $AgentLog, "AGENT", $ErrorsOnly, $ErrorPattern
}

if (-not $AgentOnly) {
    # Watch backend global log
    $BackendGlobalLog = Join-Path $BackendLogsDir "_global/run.log"
    $jobs += Start-Job -ScriptBlock {
        param($path, $src, $errsOnly, $pattern)
        $ErrorActionPreference = "Continue"
        function Write-LogLine {
            param([string]$Source, [string]$Line)
            $isError = $false
            if ($Line -match $pattern) { $isError = $true }
            if ($errsOnly -and -not $isError) { return }
            $timestamp = Get-Date -Format "HH:mm:ss"
            $prefix = "[$timestamp] [$Source]"
            if ($isError) {
                Write-Host "$prefix $Line" -ForegroundColor Red
            }
            elseif ($Line -match "WARN") {
                Write-Host "$prefix $Line" -ForegroundColor Yellow
            }
            elseif ($Line -match "INFO") {
                Write-Host "$prefix $Line" -ForegroundColor Gray
            }
            else {
                Write-Host "$prefix $Line" -ForegroundColor White
            }
        }
        if (-not (Test-Path $path)) {
            Write-Host "[monitor] waiting for $src log file: $path" -ForegroundColor Cyan
            while (-not (Test-Path $path)) { Start-Sleep -Seconds 1 }
        }
        Write-Host "[monitor] tailing $src : $path" -ForegroundColor Green
        Get-Content $path -Tail 20 -Encoding UTF8 | ForEach-Object { Write-LogLine -Source $src -Line $_ }
        Get-Content $path -Wait -Encoding UTF8 | ForEach-Object {
            if ($_ -ne "") { Write-LogLine -Source $src -Line $_ }
        }
    } -ArgumentList $BackendGlobalLog, "BACKEND", $ErrorsOnly, $ErrorPattern

    # Also watch backend per-execution logs directory for new files
    $jobs += Start-Job -ScriptBlock {
        param($dir, $pattern)
        $ErrorActionPreference = "Continue"
        if (-not (Test-Path $dir)) {
            Write-Host "[monitor] backend logs dir not found: $dir" -ForegroundColor Yellow
            return
        }
        Write-Host "[monitor] watching new execution logs in: $dir" -ForegroundColor Green
        $watcher = New-Object System.IO.FileSystemWatcher
        $watcher.Path = $dir
        $watcher.IncludeSubdirectories = $true
        $watcher.Filter = "*.log"
        $watcher.EnableRaisingEvents = $true
        $tailed = @{}
        Get-ChildItem -Path $dir -Filter "*.log" -Recurse | ForEach-Object {
            $tailed[$_.FullName] = $true
        }
        $onCreated = {
            param($sender, $e)
            $fullPath = $e.FullPath
            if (-not $tailed.ContainsKey($fullPath)) {
                $tailed[$fullPath] = $true
                $relPath = $fullPath.Replace($dir, "")
                Write-Host "[monitor] new execution log detected: $relPath" -ForegroundColor Cyan
            }
        }
        Register-ObjectEvent -InputObject $watcher -EventName Created -Action $onCreated | Out-Null
        while ($true) { Start-Sleep -Seconds 1 }
    } -ArgumentList $BackendLogsDir, $ErrorPattern
}

# Receive job output in real-time
try {
    while ($true) {
        foreach ($job in $jobs) {
            $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
            if ($output) {
                $output | Write-Host
            }
        }
        Start-Sleep -Milliseconds 200
    }
} finally {
    Write-Host "`n[monitor] stopping..." -ForegroundColor Yellow
    $jobs | Stop-Job
    $jobs | Remove-Job
}
