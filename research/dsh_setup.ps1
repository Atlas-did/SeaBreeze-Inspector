# dsh_setup.ps1 - one-shot ~/.dsh configuration (ASCII only)
# 1) switch default model to deepseek-v4-pro
# 2) register moonshotai-cn provider (for Kimi K3 subagent)
# 3) install vision-multimodal skill (configured for Kimi)
# 4) install screenshot tool
# 5) write user-level env vars
param(
    [Parameter(Mandatory=$true)][string]$SourceDir,
    [Parameter(Mandatory=$true)][string]$KimiKey
)
$ErrorActionPreference = 'Stop'
$homeRoot = $env:USERPROFILE
$dshHome  = Join-Path $homeRoot '.dsh'
$settings = Join-Path $dshHome 'settings.yaml'

Write-Host '== 1. switch model to deepseek-v4-pro + register moonshot provider =='
$yml = @'
ui-onboarding:
  welcomeNoticeVersion: 2026-08-13.1
agent-default-model:
  provider: deepseek-official
  model: deepseek-v4-pro
  reasoningEffort: high
llm-pi-ai:
  providers:
    moonshotai-cn:
      apiKeyEnv: MOONSHOT_API_KEY
'@
[System.IO.File]::WriteAllText($settings, $yml, (New-Object System.Text.UTF8Encoding $false))
Write-Host '  [OK] settings.yaml updated (Pro + moonshotai-cn)'

Write-Host '== 2. install vision-multimodal skill =='
$skillsDst = Join-Path $dshHome 'skills\vision-multimodal'
$srcSkill = Join-Path $SourceDir 'skills\vision-multimodal'
if (-not (Test-Path $srcSkill)) { throw "missing: $srcSkill" }
New-Item -ItemType Directory -Force -Path (Split-Path $skillsDst) | Out-Null
if (Test-Path $skillsDst) { Remove-Item -Recurse -Force $skillsDst }
Copy-Item -Recurse -Force $srcSkill $skillsDst
$cfg = '{"provider":"kimi","base_url":"https://api.moonshot.cn/v1","model":"moonshot-v1-8k-vision-preview"}'
[System.IO.File]::WriteAllText((Join-Path $skillsDst 'config.json'), $cfg, (New-Object System.Text.UTF8Encoding $false))
Write-Host '  [OK] skill + config.json (kimi) installed'

Write-Host '== 3. install screenshot tool =='
$toolsDst = Join-Path $dshHome 'tools\screenshot-tool'
$srcTool = Join-Path $SourceDir 'tools\screenshot-tool'
if (-not (Test-Path $srcTool)) { throw "missing: $srcTool" }
New-Item -ItemType Directory -Force -Path (Split-Path $toolsDst) | Out-Null
if (Test-Path $toolsDst) { Remove-Item -Recurse -Force $toolsDst }
Copy-Item -Recurse -Force $srcTool $toolsDst
Write-Host '  [OK] screenshot tool installed'

Write-Host '== 4. user env vars =='
[Environment]::SetEnvironmentVariable('MOONSHOT_API_KEY', $KimiKey, 'User')
[Environment]::SetEnvironmentVariable('DS_PORT', '8787', 'User')
[Environment]::SetEnvironmentVariable('DS_SHOT_DIR', (Join-Path $homeRoot 'Pictures\DeepSeek-Shots'), 'User')
Write-Host '  [OK] MOONSHOT_API_KEY / DS_PORT=8787 / DS_SHOT_DIR written'

Write-Host ''
Write-Host 'DONE. Model=Pro and moonshot provider take effect after DSH restart.'
Write-Host 'Screenshot monitor: run start-screenshot-autosave.bat in ~/.dsh/tools/screenshot-tool'
