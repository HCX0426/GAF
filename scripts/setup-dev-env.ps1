#Requires -Version 5.1
<#
.SYNOPSIS
    GAF 项目开发环境一键部署脚本
.DESCRIPTION
    在 D:\code\environment 下安装并配置完整的 GAF 开发环境：
    - Git for Windows
    - Redis for Windows
    - Miniconda3（backend 用 conda env gaf）
  - Node.js LTS（frontend 用）
  - 所有服务统一使用 conda gaf 环境
    Desktop 依赖默认不安装；如需桌面客户端，请加 -IncludeDesktop。
.NOTES
    请以管理员身份运行 PowerShell 后执行本脚本，否则部分安装可能因权限失败。
    执行：.\setup-dev-env.ps1 [-IncludeDesktop]
    开发阶段默认不安装 Desktop 依赖，如需桌面端请加上 -IncludeDesktop。
#>

param(
    [switch]$IncludeDesktop
)

# 遇到错误继续执行，但会记录
$ErrorActionPreference = "Continue"

# ---------------------------- 配置区 ----------------------------
$RootDir = "D:\code\environment"
$CondaInstallDir = "$RootDir\conda\Miniconda3"
$CondaEnvsDir = "$RootDir\conda\envs"
$CondaPkgsDir = "$RootDir\conda\pkgs"
$NodeInstallDir = "$RootDir\node\nodejs"
$NodeCacheDir = "$RootDir\node\npm-cache"
$NodeGlobalDir = "$RootDir\node\npm-global"
$GitInstallDir = "$RootDir\git"
$RedisInstallDir = "$RootDir\redis"
$PipCacheDir = "$RootDir\pip-cache"
$DownloadDir = "$RootDir\downloads"
$LogDir = "$RootDir\logs"

# 项目根目录
$ProjectRoot = "d:\code\GAF"
$BackendEnvFile = "$ProjectRoot\.env"

$LogFile = "$LogDir\setup-dev-env.log"

# ---------------------------- 辅助函数 ----------------------------
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-ToPath {
    param([string]$PathToAdd)
    $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentUserPath -notlike "*$PathToAdd*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentUserPath;$PathToAdd", "User")
        Write-Log "已添加到用户 PATH: $PathToAdd"
    } else {
        Write-Log "PATH 中已存在: $PathToAdd"
    }
    # 同步到当前进程
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

# ---------------------------- 开始安装 ----------------------------
Write-Log "=== GAF 环境初始化开始 ==="

if (-not (Test-Admin)) {
    Write-Log "请以管理员身份运行 PowerShell 后重新执行本脚本。" "ERROR"
    Write-Log "操作步骤：右键 PowerShell -> 以管理员身份运行 -> cd $ProjectRoot -> .\setup-dev-env.ps1" "ERROR"
    exit 1
}

# 创建目录结构
$dirs = @(
    $RootDir, $CondaInstallDir, $CondaEnvsDir, $CondaPkgsDir,
    $NodeInstallDir, $NodeCacheDir, $NodeGlobalDir, $GitInstallDir, $RedisInstallDir,
    $PipCacheDir, $DownloadDir, $LogDir
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Log "创建目录: $d"
    }
}

# ---------------------------- Git for Windows ----------------------------
$GitExe = "$GitInstallDir\cmd\git.exe"
if (-not (Test-Path $GitExe)) {
    Write-Log "正在查询 Git for Windows 最新版本..."
    try {
        $gitRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -UseBasicParsing
        $gitAsset = $gitRelease.assets | Where-Object { $_.name -like "Git-*-64-bit.exe" } | Select-Object -First 1
        $gitUrl = $gitAsset.browser_download_url
        $gitInstallerName = $gitAsset.name
        $gitInstallerPath = "$DownloadDir\$gitInstallerName"
        Write-Log "Git for Windows 安装包: $gitInstallerName"
    } catch {
        Write-Log "查询 Git for Windows 最新版本失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在下载 Git for Windows..."
    try {
        Invoke-WebRequest -Uri $gitUrl -OutFile $gitInstallerPath -UseBasicParsing
        Write-Log "下载完成: $gitInstallerPath"
    } catch {
        Write-Log "下载 Git for Windows 失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在静默安装 Git for Windows 到 $GitInstallDir ..."
    $gitInstallArgs = "/SILENT /NORESTART /DIR=`"$GitInstallDir`""
    $gitProc = Start-Process -FilePath $gitInstallerPath -ArgumentList $gitInstallArgs -Wait -PassThru
    if ($gitProc.ExitCode -ne 0) {
        Write-Log "Git for Windows 安装失败，退出码: $($gitProc.ExitCode)" "ERROR"
        exit 1
    }
    Write-Log "Git for Windows 安装完成"
} else {
    Write-Log "Git for Windows 已存在，跳过安装"
}

# 配置 Git 用户信息
& $GitExe config --global user.name "HCX0426"
& $GitExe config --global user.email "chongxuan-huang@outlook.com"
Write-Log "已配置 Git 用户信息"

# ---------------------------- Redis for Windows ----------------------------
$RedisServerExe = "$RedisInstallDir\redis-server.exe"
if (-not (Test-Path $RedisServerExe)) {
    Write-Log "正在查询 Redis for Windows 最新版本..."
    try {
        $redisRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/tporadowski/redis/releases/latest" -UseBasicParsing
        $redisAsset = $redisRelease.assets | Where-Object { $_.name -like "Redis-x64-*.zip" } | Select-Object -First 1
        $redisUrl = $redisAsset.browser_download_url
        $redisZipName = $redisAsset.name
        $redisZipPath = "$DownloadDir\$redisZipName"
        Write-Log "Redis for Windows 安装包: $redisZipName"
    } catch {
        Write-Log "查询 Redis for Windows 最新版本失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在下载 Redis for Windows..."
    try {
        Invoke-WebRequest -Uri $redisUrl -OutFile $redisZipPath -UseBasicParsing
        Write-Log "下载完成: $redisZipPath"
    } catch {
        Write-Log "下载 Redis for Windows 失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在解压 Redis for Windows 到 $RedisInstallDir ..."
    Expand-Archive -Path $redisZipPath -DestinationPath "$RootDir\redis-temp" -Force
    # 如果解压后有多层目录，把内容移到目标目录
    $extractedItems = Get-ChildItem -Path "$RootDir\redis-temp" -Force
    if ($extractedItems.Count -eq 1 -and $extractedItems[0].PSIsContainer) {
        Get-ChildItem -Path $extractedItems[0].FullName | Move-Item -Destination $RedisInstallDir -Force
    } else {
        Get-ChildItem -Path "$RootDir\redis-temp" | Move-Item -Destination $RedisInstallDir -Force
    }
    Remove-Item -Path "$RootDir\redis-temp" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Log "Redis for Windows 解压完成"
} else {
    Write-Log "Redis for Windows 已存在，跳过安装"
}

# ---------------------------- Miniconda3 ----------------------------
$CondaExe = "$CondaInstallDir\condabin\conda.bat"
$CondaProfile = "$CondaInstallDir\.condarc"

if (-not (Test-Path $CondaExe)) {
    $MinicondaUrl = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    $MinicondaInstaller = "$DownloadDir\Miniconda3-latest-Windows-x86_64.exe"

    Write-Log "正在下载 Miniconda3..."
    try {
        Invoke-WebRequest -Uri $MinicondaUrl -OutFile $MinicondaInstaller -UseBasicParsing
        Write-Log "下载完成: $MinicondaInstaller"
    } catch {
        Write-Log "下载 Miniconda3 失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在静默安装 Miniconda3 到 $CondaInstallDir ..."
    $installArgs = "/S /D=$CondaInstallDir"
    $proc = Start-Process -FilePath $MinicondaInstaller -ArgumentList $installArgs -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Log "Miniconda3 安装失败，退出码: $($proc.ExitCode)" "ERROR"
        exit 1
    }
    Write-Log "Miniconda3 安装完成"
} else {
    Write-Log "Miniconda3 已存在，跳过安装"
}

# 配置 conda envs/pkgs 路径到 D 盘，并使用清华镜像加速
# 先删除旧配置避免重复 key，再用 conda config 命令确保被正确识别
if (Test-Path $CondaProfile) {
    Remove-Item -Path $CondaProfile -Force
    Write-Log "已清理旧 conda 配置: $CondaProfile"
}
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add envs_dirs $CondaEnvsDir | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add pkgs_dirs $CondaPkgsDir | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add channels defaults | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add channels "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/" | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add channels "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/" | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --add channels "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/" | Out-Null
& "$CondaInstallDir\Scripts\conda.exe" config --file $CondaProfile --set show_channel_urls true | Out-Null
Write-Log "已写入 conda 配置: $CondaProfile"

# 初始化 conda 供 PowerShell 使用
& "$CondaInstallDir\Scripts\conda.exe" init powershell | Out-Null
Write-Log "已初始化 conda for PowerShell"

# ---------------------------- Node.js LTS ----------------------------
$NodeExe = "$NodeInstallDir\node.exe"
$NpmExe = "$NodeInstallDir\npm.cmd"

if (-not (Test-Path $NodeExe)) {
    Write-Log "正在查询 Node.js LTS 最新版本..."
    try {
        $nodeReleases = Invoke-RestMethod -Uri "https://nodejs.org/dist/index.json" -UseBasicParsing
        $latestLts = $nodeReleases | Where-Object { $_.lts -ne $false } | Select-Object -First 1
        $nodeVersion = $latestLts.version
        $nodeZip = "node-$nodeVersion-win-x64.zip"
        $nodeUrl = "https://nodejs.org/dist/$nodeVersion/$nodeZip"
        $nodeZipPath = "$DownloadDir\$nodeZip"
        Write-Log "Node.js LTS 版本: $nodeVersion"
    } catch {
        Write-Log "查询 Node.js LTS 失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在下载 Node.js $nodeVersion ..."
    try {
        Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZipPath -UseBasicParsing
        Write-Log "下载完成: $nodeZipPath"
    } catch {
        Write-Log "下载 Node.js 失败: $_" "ERROR"
        exit 1
    }

    Write-Log "正在解压 Node.js 到 $NodeInstallDir ..."
    Expand-Archive -Path $nodeZipPath -DestinationPath "$RootDir\node" -Force
    # 解压后文件夹名为 node-x.x.x-win-x64，需要重命名
    $extractedDir = "$RootDir\node\node-$nodeVersion-win-x64"
    if (Test-Path $extractedDir) {
        # 先清空目标目录（如果有残留）
        if (Test-Path $NodeInstallDir) {
            Remove-Item -Recurse -Force $NodeInstallDir -Confirm:$false -ErrorAction SilentlyContinue
        }
        Rename-Item -Path $extractedDir -NewName $NodeInstallDir -Force
        Write-Log "Node.js 解压完成"
    }
} else {
    Write-Log "Node.js 已存在，跳过安装"
}

# 配置 npm 缓存、全局包到 D 盘，并使用腾讯镜像加速
& $NpmExe config set cache "$NodeCacheDir" --global
& $NpmExe config set prefix "$NodeGlobalDir" --global
& $NpmExe config set registry "https://mirrors.cloud.tencent.com/npm/" --global
Write-Log "已配置 npm cache=$NodeCacheDir, prefix=$NodeGlobalDir, registry=腾讯镜像"

# 更新 PATH（当前用户）
Add-ToPath -PathToAdd "$CondaInstallDir\condabin"
Add-ToPath -PathToAdd "$CondaInstallDir\Scripts"
Add-ToPath -PathToAdd $NodeInstallDir
Add-ToPath -PathToAdd "$NodeGlobalDir"
Add-ToPath -PathToAdd "$GitInstallDir\cmd"
Add-ToPath -PathToAdd $RedisInstallDir

# ---------------------------- conda env gaf ----------------------------
$GafEnvPython = "$CondaEnvsDir\gaf\python.exe"
if (-not (Test-Path $GafEnvPython)) {
    # 新版 conda 需要接受默认 channel 的服务条款
    Write-Log "正在接受 Anaconda 默认 channel 服务条款..."
    & "$CondaInstallDir\Scripts\conda.exe" tos accept --override-channels --channel "https://repo.anaconda.com/pkgs/main" | Out-Null
    & "$CondaInstallDir\Scripts\conda.exe" tos accept --override-channels --channel "https://repo.anaconda.com/pkgs/r" | Out-Null
    & "$CondaInstallDir\Scripts\conda.exe" tos accept --override-channels --channel "https://repo.anaconda.com/pkgs/msys2" | Out-Null

    $envYml = "$ProjectRoot\environment.yml"
    if (Test-Path $envYml) {
        Write-Log "正在从 $envYml 创建 conda env gaf ..."
        & "$CondaInstallDir\Scripts\conda.exe" env create -f $envYml -y
        if ($LASTEXITCODE -ne 0) {
            Write-Log "创建 gaf env 失败" "ERROR"
            exit 1
        }
        Write-Log "gaf env 创建完成"
    } else {
        Write-Log "未找到 environment.yml: $envYml" "ERROR"
        exit 1
    }
} else {
    Write-Log "conda env gaf 已存在，跳过创建"
}

# ---------------------------- 项目依赖安装 ----------------------------

# 配置 pip 使用清华镜像和 D 盘缓存（pip.ini 不能带 BOM）
$pipConfigDir = "$env:APPDATA\pip"
if (-not (Test-Path $pipConfigDir)) {
    New-Item -ItemType Directory -Path $pipConfigDir -Force | Out-Null
}
$pipIniContent = "[global]`nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple`ntrusted-host = pypi.tuna.tsinghua.edu.cn`ncache-dir = $PipCacheDir`n"
[System.IO.File]::WriteAllText("$pipConfigDir\pip.ini", $pipIniContent, (New-Object System.Text.UTF8Encoding $false))
Write-Log "已配置 pip 清华镜像和缓存目录"

# backend 依赖（即使 gaf env 已存在也重新安装，确保完整）
$BackendReq = "$ProjectRoot\backend\requirements\dev.txt"
if (Test-Path $BackendReq) {
    Write-Log "正在安装 backend 依赖..."
    & $GafEnvPython -m pip install --cache-dir $PipCacheDir -r $BackendReq
    if ($LASTEXITCODE -ne 0) {
        Write-Log "安装 backend 依赖失败" "ERROR"
    } else {
        Write-Log "backend 依赖安装完成"
    }
} else {
    Write-Log "未找到 backend/requirements/dev.txt，跳过" "WARN"
}

# agent 依赖
$AgentReq = "$ProjectRoot\agent\requirements.txt"
if (Test-Path $AgentReq) {
    Write-Log "正在安装 agent 依赖 (统一到 conda gaf 环境)..."
    & $GafEnvPython -m pip install --cache-dir $PipCacheDir -r $AgentReq
    if ($LASTEXITCODE -ne 0) {
        Write-Log "安装 agent 依赖失败" "ERROR"
    } else {
        Write-Log "agent 依赖安装完成"
    }
} else {
    Write-Log "未找到 agent/requirements.txt，跳过" "WARN"
}

# frontend 依赖
$FrontendDir = "$ProjectRoot\frontend"
$DesktopDir = "$ProjectRoot\desktop"

# desktop 依赖（开发阶段默认跳过，需加 -IncludeDesktop 才安装）
if ($IncludeDesktop) {
    if (Test-Path "$DesktopDir\package.json") {
        Write-Log "正在安装 desktop npm 依赖..."
        Push-Location $DesktopDir
        & $NpmExe install
        if ($LASTEXITCODE -ne 0) {
            Write-Log "安装 desktop 依赖失败" "ERROR"
        } else {
            Write-Log "desktop 依赖安装完成"
        }
        Pop-Location
    } else {
        Write-Log "未找到 desktop/package.json，跳过" "WARN"
    }
} else {
    Write-Log "开发阶段跳过 desktop 依赖安装（如需请使用 -IncludeDesktop）" "INFO"
}

if (Test-Path "$FrontendDir\package.json") {
    Write-Log "正在安装 frontend npm 依赖..."
    Push-Location $FrontendDir
    & $NpmExe install
    if ($LASTEXITCODE -ne 0) {
        Write-Log "安装 frontend 依赖失败" "ERROR"
    } else {
        Write-Log "frontend 依赖安装完成"
    }
    Pop-Location
} else {
    Write-Log "未找到 frontend/package.json，跳过" "WARN"
}

# ---------------------------- .env 模板 ----------------------------
if (-not (Test-Path $BackendEnvFile)) {
    $EnvExample = "$ProjectRoot\.env.example"
    if (Test-Path $EnvExample) {
        Copy-Item -Path $EnvExample -Destination $BackendEnvFile
        Write-Log "已复制 .env.example 到 .env，请按需修改"
    }
}

# ---------------------------- 安装后验证 ----------------------------
Write-Log ""
Write-Log "=== 安装后验证 ==="

$condaVersion = & "$CondaInstallDir\Scripts\conda.exe" --version 2>&1
Write-Log "conda 版本: $condaVersion"

$nodeVersion = & $NodeExe --version 2>&1
Write-Log "node 版本: $nodeVersion"

$npmVersion = & $NpmExe --version 2>&1
Write-Log "npm 版本: $npmVersion"

$gitVersion = & $GitExe --version 2>&1
Write-Log "git 版本: $gitVersion"

$redisVersion = & "$RedisInstallDir\redis-server.exe" --version 2>&1
Write-Log "redis 版本: $redisVersion"

$gafVersion = & $GafEnvPython --version 2>&1
Write-Log "gaf env Python 版本: $gafVersion"

Write-Log ""
Write-Log "=== 安装摘要 ==="
Write-Log "Miniconda3: $CondaInstallDir"
Write-Log "conda env gaf: $CondaEnvsDir\gaf"
Write-Log "Node.js: $NodeInstallDir"
Write-Log "npm cache: $NodeCacheDir"
Write-Log "Git: $GitInstallDir"
Write-Log "Redis: $RedisInstallDir"
Write-Log "pip cache: $PipCacheDir"
Write-Log "日志文件: $LogFile"
Write-Log ""
Write-Log "=== 后续操作 ==="
Write-Log "1. 重新打开 PowerShell，使 PATH 生效"
Write-Log "2. 一键启动: .\start.bat  或  .\start.ps1"
Write-Log "3. 一键停止: .\stop.bat"
Write-Log "4. 手动启动后端: conda activate gaf && cd backend && python -m daphne config.asgi:application -b 0.0.0.0 -p 8000"
Write-Log "5. 手动启动 Agent: conda activate gaf && cd agent && python -m src"
Write-Log "6. 手动启动前端: cd frontend && npm run dev"
Write-Log "7. 手动启动桌面（如已 -IncludeDesktop 安装）: cd desktop && npm run dev"
Write-Log "=== GAF 环境初始化完成 ==="

# ---------------------------- 最终健康检查 ----------------------------
Write-Log ""
Write-Log "=== 环境健康检查 ==="

$allOk = $true

# Git
if (-not (Test-Path $GitExe)) {
    $allOk = $false
    Write-Log "Git 未安装" "ERROR"
} else {
    Write-Log "Git: OK"
}

# Git 用户信息
$gitName = & $GitExe config --global user.name 2>$null
$gitEmail = & $GitExe config --global user.email 2>$null
if (-not $gitName -or -not $gitEmail) {
    $allOk = $false
    Write-Log "Git 用户信息未配置" "ERROR"
} else {
    Write-Log "Git 用户信息: OK ($gitName / $gitEmail)"
}

# Redis
if (-not (Test-Path $RedisServerExe)) {
    $allOk = $false
    Write-Log "Redis 未安装" "ERROR"
} else {
    Write-Log "Redis: OK"
}

# Conda
if (-not (Test-Path $CondaExe)) {
    $allOk = $false
    Write-Log "Conda 未安装" "ERROR"
} else {
    Write-Log "Conda: OK"
}

# gaf env
if (-not (Test-Path $GafEnvPython)) {
    $allOk = $false
    Write-Log "conda env gaf 未创建" "ERROR"
} else {
    Write-Log "conda env gaf: OK"
}

# Node.js
if (-not (Test-Path $NodeExe)) {
    $allOk = $false
    Write-Log "Node.js 未安装" "ERROR"
} else {
    Write-Log "Node.js: OK"
}

# conda envs/pkgs 路径配置
$condaEnvDirs = & "$CondaInstallDir\Scripts\conda.exe" config --show envs_dirs 2>$null
if (-not ($condaEnvDirs -like "*$CondaEnvsDir*")) {
    $allOk = $false
    Write-Log "conda envs_dirs 未配置到 D 盘: $CondaEnvsDir" "ERROR"
} else {
    Write-Log "conda envs_dirs: OK"
}

$condaPkgsDirs = & "$CondaInstallDir\Scripts\conda.exe" config --show pkgs_dirs 2>$null
if (-not ($condaPkgsDirs -like "*$CondaPkgsDir*")) {
    $allOk = $false
    Write-Log "conda pkgs_dirs 未配置到 D 盘: $CondaPkgsDir" "ERROR"
} else {
    Write-Log "conda pkgs_dirs: OK"
}

# pip cache 路径配置
$pipCacheConfig = & $AgentPython -m pip config get global.cache-dir 2>$null
if ($pipCacheConfig -ne $PipCacheDir) {
    $allOk = $false
    Write-Log "pip cache-dir 未配置到 D 盘: 期望 $PipCacheDir, 实际 $pipCacheConfig" "ERROR"
} else {
    Write-Log "pip cache-dir: OK"
}

# npm cache/prefix 路径配置
$npmCacheConfig = & $NpmExe config get cache 2>$null
if ($npmCacheConfig -ne $NodeCacheDir) {
    $allOk = $false
    Write-Log "npm cache 未配置到 D 盘: $NodeCacheDir" "ERROR"
} else {
    Write-Log "npm cache: OK"
}

$npmPrefixConfig = & $NpmExe config get prefix 2>$null
if ($npmPrefixConfig -ne $NodeGlobalDir) {
    $allOk = $false
    Write-Log "npm prefix 未配置到 D 盘: $NodeGlobalDir" "ERROR"
} else {
    Write-Log "npm prefix: OK"
}

# frontend node_modules
if (-not (Test-Path "$FrontendDir\node_modules")) {
    $allOk = $false
    Write-Log "frontend node_modules 不存在" "ERROR"
} else {
    Write-Log "frontend 依赖: OK"
}

# desktop node_modules（仅在显式安装桌面端时检查）
if ($IncludeDesktop) {
    if (-not (Test-Path "$DesktopDir\node_modules")) {
        $allOk = $false
        Write-Log "desktop node_modules 不存在" "ERROR"
    } else {
        Write-Log "desktop 依赖: OK"
    }
}

# .env
if (-not (Test-Path $BackendEnvFile)) {
    $allOk = $false
    Write-Log ".env 文件不存在" "ERROR"
} else {
    Write-Log ".env: OK"
}

Write-Log ""
if ($allOk) {
    Write-Log "=== 所有检查通过，开发环境已就绪 ==="
} else {
    Write-Log "=== 部分检查未通过，请查看上方 ERROR 日志 ===" "ERROR"
    exit 1
}
