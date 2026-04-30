param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ViteArgs
)

$ErrorActionPreference = "Stop"

$frontendRoot = $PSScriptRoot
$dependencyRoot = "C:\temp\mi-asistente-frontend-deps"

& (Join-Path $frontendRoot "setup-frontend-deps.ps1") -DependencyRoot $dependencyRoot

$resolvedArgs = @()
if ($ViteArgs.Count -eq 0) {
    $resolvedArgs += "dev"
} else {
    $resolvedArgs += $ViteArgs
}

if ($resolvedArgs[0] -eq "dev" -or $resolvedArgs[0] -eq "preview") {
    $resolvedArgs += "--host"
    $resolvedArgs += "127.0.0.1"
}

$runtimeSuffix = "{0}-{1}" -f $resolvedArgs[0], $PID
$runtimeRoot = Join-Path "C:\temp" ("mi-asistente-frontend-runtime-" + $runtimeSuffix)

if (Test-Path $runtimeRoot) {
    Remove-Item -Recurse -Force $runtimeRoot
}

New-Item -ItemType Directory -Path $runtimeRoot | Out-Null

foreach ($fileName in @("index.html", "package.json", "vite.config.js")) {
    $sourcePath = Join-Path $frontendRoot $fileName
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath (Join-Path $runtimeRoot $fileName) -Force
    }
}

foreach ($directoryName in @("src", "public")) {
    $sourcePath = Join-Path $frontendRoot $directoryName
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath (Join-Path $runtimeRoot $directoryName) -Recurse -Force
    }
}

$runtimeNodeModules = Join-Path $runtimeRoot "node_modules"
cmd /c mklink /J "$runtimeNodeModules" "$dependencyRoot\node_modules" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not create runtime node_modules junction in $runtimeRoot"
}

Push-Location $runtimeRoot
try {
    npm exec vite -- @resolvedArgs
    $viteExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($viteExitCode -eq 0 -and $resolvedArgs[0] -eq "build") {
    $workspaceDist = Join-Path $frontendRoot "dist"
    $runtimeDist = Join-Path $runtimeRoot "dist"

    if (Test-Path $workspaceDist) {
        Remove-Item -Recurse -Force $workspaceDist
    }

    if (Test-Path $runtimeDist) {
        Copy-Item $runtimeDist $workspaceDist -Recurse -Force
    }
}

exit $viteExitCode