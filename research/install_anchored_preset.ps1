# install_anchored_preset.ps1 - install dsh-anchored-standard preset (ASCII only)
# Copies the preset dir into ~/.dsh/.agent-presets/anchored-standard
# Usage: powershell -ExecutionPolicy Bypass -File install_anchored_preset.ps1 -SourceDir <dir>
param([Parameter(Mandatory=$true)][string]$SourceDir)
$ErrorActionPreference = 'Stop'
$dst = Join-Path $env:USERPROFILE '.dsh\.agent-presets\anchored-standard'

# find the dir that contains agent.cordis.yml (repo root or one level down)
$presetDir = $null
if (Test-Path (Join-Path $SourceDir 'agent.cordis.yml')) {
    $presetDir = $SourceDir
} else {
    Get-ChildItem -Path $SourceDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-Path (Join-Path $_.FullName 'agent.cordis.yml')) { $presetDir = $_.FullName }
    }
}
if (-not $presetDir) { throw "agent.cordis.yml not found under $SourceDir" }
Write-Host "preset dir: $presetDir"

New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse -Force $presetDir $dst
Write-Host "[OK] preset installed to $dst"
Write-Host "Next: restart DSH, open a NEW session, select 'anchored-standard' in the preset picker."
