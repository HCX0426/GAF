# gaf_capture.ps1 — PowerShell 5 UTF-8 命令捕获 helper (N92 Layer 3 修复)
#
# Why: PowerShell 5 native command stdout 接收时按系统编码 (cp936) 解码,
#      即便 Python 端已输出 UTF-8 字节,管道里也会变成 mojibake.
# Fix: 重定向到文件 + UTF-8 读取,绕过 PowerShell 5 stdout 解码 bug.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File GAF\scripts\gaf_capture.ps1 -Command "python GAF/scripts/sync_ai_memory.py"
#   powershell -ExecutionPolicy Bypass -File GAF\scripts\gaf_capture.ps1 -Command "git status" -Head 10

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [int]$Head = 50,
    [switch]$ShowCommand,
    [string]$TempFile = "$env:TEMP\gaf_capture_$PID.txt"
)

# 1. 强制 UTF-8 环境
$env:PYTHONIOENCODING = 'utf-8'
$env:LC_ALL = 'C.UTF-8'
$env:PYTHONUTF8 = '1'
$env:GIT_TERMINAL_PROMPT = '0'

# 2. 清理上次残留
if (Test-Path $TempFile) {
    Remove-Item -Force $TempFile
}

# 3. 执行命令 + 重定向到文件
if ($ShowCommand) {
    Write-Host ">>> $Command" -ForegroundColor Cyan
}

# 用 PowerShell 原生调用,不走 cmd /c（避免 cmd 编码层）
Invoke-Expression $Command > $TempFile 2>&1
$exitCode = $LASTEXITCODE

# 4. 用 UTF-8 读取文件内容
if (Test-Path $TempFile) {
    $content = Get-Content -Raw -Encoding UTF8 $TempFile
    if ($Head -gt 0 -and $content) {
        $lines = $content -split "`n"
        $content = ($lines | Select-Object -First $Head) -join "`n"
    }
    if ($content) {
        Write-Host $content
    } else {
        Write-Host "(无输出)" -ForegroundColor DarkGray
    }
    Remove-Item -Force $TempFile
} else {
    Write-Host "(无输出)" -ForegroundColor DarkGray
}

# 5. 透传 exit code
exit $exitCode
