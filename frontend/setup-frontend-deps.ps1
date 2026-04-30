param(
    [string]$DependencyRoot = "C:\temp\mi-asistente-frontend-deps"
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = $PSScriptRoot

Write-Host "Preparing frontend dependencies in $DependencyRoot"

New-Item -ItemType Directory -Force -Path $DependencyRoot | Out-Null
Copy-Item (Join-Path $frontendRoot "package.json") (Join-Path $DependencyRoot "package.json") -Force

$lockFile = Join-Path $frontendRoot "package-lock.json"
if (Test-Path $lockFile) {
    Copy-Item $lockFile (Join-Path $DependencyRoot "package-lock.json") -Force
}

Push-Location $DependencyRoot
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host "Frontend dependencies ready in $DependencyRoot"