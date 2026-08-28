#!/usr/bin/env pwsh
<#
.SYNOPSIS
    生成本地开发自签 TLS 证书，用于 Daphne HTTPS / Agent wss:// 测试

.DESCRIPTION
    使用 OpenSSL 生成 ca.pem（CA 根证书）、server-cert.pem（服务端证书）、server-key.pem（服务端私钥）。
    Agent 端可设置 GAF_SSL_CA_FILE=certs/ca.pem 来信任自签 CA。

.NOTES
    仅用于本地开发环境，生产环境请使用 Let's Encrypt 等正式 CA 签发的证书。
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

openssl version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "请先安装 OpenSSL（https://slproweb.com/products/Win32OpenSSL.html）"
    exit 1
}

$days = 3650
$subj = "/C=CN/ST=Dev/L=Local/O=GAF/CN=localhost"

Write-Host "=== 生成 CA 根证书 ===" -ForegroundColor Cyan
openssl req -x509 -newkey rsa:4096 -keyout ca-key.pem -out ca.pem -days $days -nodes `
    -subj $subj 2>$null

Write-Host "=== 生成服务端 CSR ===" -ForegroundColor Cyan
openssl req -new -newkey rsa:2048 -keyout server-key.pem -out server.csr -nodes `
    -subj $subj 2>$null

Write-Host "=== CA 签发服务端证书 ===" -ForegroundColor Cyan
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial `
    -out server-cert.pem -days $days 2>$null

Remove-Item server.csr, ca-key.pem, ca.srl -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== 证书已生成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "  服务端证书: certs/server-cert.pem" -ForegroundColor Green
Write-Host "  服务端私钥: certs/server-key.pem" -ForegroundColor Green
Write-Host "  CA 根证书:  certs/ca.pem" -ForegroundColor Green
Write-Host ""
Write-Host "=== 启动带 TLS 的 Daphne ===" -ForegroundColor Cyan
Write-Host "  daphne --ssl-certfile=certs/server-cert.pem --ssl-keyfile=certs/server-key.pem -e ssl:8443:privateKey=certs/server-key.pem:certKey=certs/server-cert.pem config.asgi:application"
Write-Host ""
Write-Host "=== Agent 端配置（.env）===" -ForegroundColor Cyan
Write-Host "  # 默认 WS 路径为 ws/protocol/agents/，可通过 GAF_WS_AGENT_PATH 环境变量覆盖"
Write-Host "  GAF_SERVER_URL=wss://localhost:8443/\${GAF_WS_AGENT_PATH:-ws/protocol/agents/}"
Write-Host "  GAF_SSL_CA_FILE=certs/ca.pem"