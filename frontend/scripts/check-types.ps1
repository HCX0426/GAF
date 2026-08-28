#!/usr/bin/env pwsh
# check-types.ps1 - Phase 2 / N197 / N192: frontend TypeScript type-check entry
#
# Purpose:
#   Run `tsc --noEmit` against frontend/src production code.
#   Non-zero exit on failure to block merges that violate type contracts.
#   Skips __tests__ (Vitest tests use vi.mock for planned-not-yet-implemented
#   modules; the runtime test loader handles them, not the TS compiler).
#
# Usage:
#   Local:  ./frontend/scripts/check-types.ps1
#   CI:     pwsh ./frontend/scripts/check-types.ps1
#
# Exit codes:
#   0 = pass
#   1 = type errors found
#   2 = tsc not installed

[CmdletBinding()]
param(
    [switch]$WarnOnly
)

$ErrorActionPreference = 'Stop'
$FrontendRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $FrontendRoot

Write-Host "[TS] TypeScript type-check (noImplicitAny enabled)..."

# Resolve tsc. On Windows the dev setup has node_modules hoisted to repo root
# (pnpm-workspace-style), so check both places.
$tscCandidates = @(
    (Join-Path $FrontendRoot "node_modules\.bin\tsc.cmd"),
    (Join-Path $RepoRoot "node_modules\.bin\tsc.cmd")
)
$tscPath = $tscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $tscPath) {
    Write-Host "ERROR: tsc not installed. Run: cd frontend; npm ci"
    exit 2
}
Write-Host "[TS] Using $tscPath"

Push-Location $FrontendRoot
try {
    & $tscPath --noEmit --project tsconfig.app.json
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($exitCode -eq 0) {
    Write-Host "OK: Type-check passed (0 errors)"
    exit 0
}

if ($WarnOnly) {
    Write-Host "WARN: Type errors found (WarnOnly mode, not blocking)"
    exit 0
}

Write-Host "ERROR: Type-check failed (exit=$exitCode). Fix the errors above."
Write-Host "       Production code is checked with noImplicitAny."
Write-Host "       Use -WarnOnly to bypass locally (NEVER do this in CI)."
exit 1
