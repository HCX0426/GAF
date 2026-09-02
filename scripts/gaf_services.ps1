<#
.SYNOPSIS
  GAF 统一服务管理脚本 — 兼容层 (TD-352, 2026-08-08)

.DESCRIPTION
  TD-352: 此脚本的 start/stop/restart/status 命令已委托给
  ``scripts/gaf_daemon.py`` Python 守护进程, 后者提供:
    - 看门狗循环 (自动重启崩溃的服务)
    - 按依赖顺序启动/停止
    - 信号处理 (Ctrl+C 优雅关闭)
    - 重启次数限制 (30 分钟内最多 3 次)

  保留 logs 命令 (日志查看功能).

  使用方法:
    powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 start     # 启动全部 (daemon 模式)
    powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 stop      # 停止全部
    powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 restart   # 重启全部
    powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 status    # 查看状态
    powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 logs      # 查看日志

  日志位置 (全部统一到 d:/code/GAF/debug/):
    - Redis: 控制台输出 (后台运行, 不落盘)
    - Backend: d:/code/GAF/debug/run.log (FileLogHandler 自动写)
    - Agent:   d:/code/GAF/debug/agent.log
    - Frontend: d:/code/GAF/debug/frontend.log
    - Daemon:  d:/code/GAF/debug/daemon.log (gaf_daemon.py 自身日志)
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$GafRoot = Resolve-Path "$PSScriptRoot/.."

# Auto-discover the conda gaf python.exe (mirrors gaf_init.ps1 discovery).
function Get-GafPython {
    # 1. CONDA_PREFIX points at the active env's install root.
    if ($env:CONDA_PREFIX -and (Test-Path "$env:CONDA_PREFIX\python.exe")) {
        return "$env:CONDA_PREFIX\python.exe"
    }
    # 2. Resolve conda.exe location to derive the default envs dir.
    $condaExe = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaExe) {
        try {
            $envs = & $condaExe.Source env list 2>$null | Select-String -Pattern "\sgaf\s" 
            if ($envs) {
                $gafPath = ($envs[0].Line -split "\s+")[0]
                if ($gafPath -and (Test-Path "$gafPath\python.exe")) {
                    return "$gafPath\python.exe"
                }
            }
        } catch { }
    }
    # 3. Fall back to common install locations.
    $candidates = @(
        "D:\code\environment\conda\envs\gaf\python.exe",
        "D:\code\environment\Miniconda3\envs\gaf\python.exe",
        "$env:USERPROFILE\Miniconda3\envs\gaf\python.exe",
        "$env:USERPROFILE\Anaconda3\envs\gaf\python.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) { return $cand }
    }
    # 4. Last resort: rely on python on PATH.
    return $null
}

$PythonExe = Get-GafPython
if (-not $PythonExe) {
    $PythonExe = "python"
}
$DaemonScript = Join-Path $GafRoot "scripts\gaf_daemon.py"

switch ($Action) {
    "start" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  GAF 服务启动 (后台模式, TD-352)" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        & $PythonExe $DaemonScript start
    }
    "stop" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  GAF 服务停止" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        & $PythonExe $DaemonScript stop
    }
    "restart" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  GAF 服务重启" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        & $PythonExe $DaemonScript restart
    }
    "status" {
        & $PythonExe $DaemonScript status
    }
    "logs" {
        # N194 归一化后, 三个服务的日志都在 d:/code/GAF/debug/ 下
        # backend.log/agent.log/frontend.log, 这里用 Get-Content -Wait 多文件并行 tail
        $DebugDir = Join-Path $GafRoot "debug"
        $Logs = @(
            @{Name="backend";  Path=(Join-Path $DebugDir "run.log")},
            @{Name="agent";    Path=(Join-Path $DebugDir "agent.log")},
            @{Name="frontend"; Path=(Join-Path $DebugDir "frontend.log")}
        )
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  GAF 统一日志查看 (Ctrl+C 退出)" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        foreach ($l in $Logs) {
            if (Test-Path $l.Path) {
                $size = (Get-Item $l.Path).Length
                Write-Host "  [$($l.Name)] $($l.Path) ($([math]::Round($size/1KB, 1)) KB)" -ForegroundColor Green
            } else {
                Write-Host "  [$($l.Name)] $($l.Path) (不存在, 启动服务后会自动创建)" -ForegroundColor Gray
            }
        }
        Write-Host ""
        # 并行 tail 所有存在的日志, 带 service 前缀
        $jobs = @()
        foreach ($l in $Logs) {
            if (Test-Path $l.Path) {
                $jobs += Start-Job -ScriptBlock {
                    param($name, $path)
                    Get-Content $path -Wait -Tail 20 -Encoding UTF8 | ForEach-Object {
                        Write-Host "[$name] $_"
                    }
                } -ArgumentList $l.Name, $l.Path
            }
        }
        if ($jobs.Count -eq 0) {
            Write-Host "❌ 无日志文件, 请先启动服务: powershell -File scripts\gaf_services.ps1 start" -ForegroundColor Red
        } else {
            Write-Host "实时 tail 中 (Ctrl+C 退出)..." -ForegroundColor Yellow
            while ($true) {
                Start-Sleep -Seconds 1
                foreach ($job in $jobs) {
                    if ($job.State -ne 'Running') {
                        Write-Host "⚠️ 日志 job 退出: $($job.Id)" -ForegroundColor Red
                    }
                }
            }
        }
    }
}
