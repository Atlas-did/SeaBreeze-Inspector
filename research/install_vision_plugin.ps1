# install_vision_plugin.ps1
# 把 dsh-vision-complete 安装到 ~\.dsh（skill + 截图工具），并配置为 Kimi 视觉模型。
# 用法：powershell -ExecutionPolicy Bypass -File .\install_vision_plugin.ps1
# 参数：
#   -SourceDir   解压后的 dsh-vision-complete-main 目录
#   -KimiKey     Kimi / Moonshot API Key
param(
    [Parameter(Mandatory=$true)][string]$SourceDir,
    [Parameter(Mandatory=$true)][string]$KimiKey
)
$ErrorActionPreference = 'Stop'
$homeRoot = $env:USERPROFILE
$skillsDst = Join-Path $homeRoot '.dsh\skills\vision-multimodal'
$toolsDst  = Join-Path $homeRoot '.dsh\tools\screenshot-tool'

Write-Host '== 1. 安装 skill ==' -ForegroundColor Cyan
$srcSkill = Join-Path $SourceDir 'skills\vision-multimodal'
if (-not (Test-Path $srcSkill)) { throw "找不到 $srcSkill" }
New-Item -ItemType Directory -Force -Path (Split-Path $skillsDst) | Out-Null
if (Test-Path $skillsDst) { Remove-Item -Recurse -Force $skillsDst }
Copy-Item -Recurse -Force $srcSkill $skillsDst
Write-Host '  [OK] skill 已安装' -ForegroundColor Green

Write-Host '== 2. 写入 Kimi 配置 ==' -ForegroundColor Cyan
$cfg = @'
{
  "provider": "kimi",
  "base_url": "https://api.moonshot.cn/v1",
  "model": "moonshot-v1-8k-vision-preview"
}
'@
[System.IO.File]::WriteAllText((Join-Path $skillsDst 'config.json'), $cfg, (New-Object System.Text.UTF8Encoding $false))
Write-Host '  [OK] config.json (provider=kimi) 已写入' -ForegroundColor Green

Write-Host '== 3. 安装截图工具 ==' -ForegroundColor Cyan
$srcTool = Join-Path $SourceDir 'tools\screenshot-tool'
if (-not (Test-Path $srcTool)) { throw "找不到 $srcTool" }
New-Item -ItemType Directory -Force -Path (Split-Path $toolsDst) | Out-Null
if (Test-Path $toolsDst) { Remove-Item -Recurse -Force $toolsDst }
Copy-Item -Recurse -Force $srcTool $toolsDst
Write-Host '  [OK] 截图工具已安装' -ForegroundColor Green

Write-Host '== 4. 设置环境变量（用户级，重启终端/重启 DSH 后生效） ==' -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable('MOONSHOT_API_KEY', $KimiKey, 'User')
# 本机 DSH Web GUI 端口是 8787（非默认 3080）
[Environment]::SetEnvironmentVariable('DS_PORT', '8787', 'User')
[Environment]::SetEnvironmentVariable('DS_SHOT_DIR', (Join-Path $homeRoot 'Pictures\DeepSeek-Shots'), 'User')
Write-Host '  [OK] MOONSHOT_API_KEY / DS_PORT=8787 / DS_SHOT_DIR 已写入用户环境变量' -ForegroundColor Green

Write-Host ''
Write-Host '安装完成。下一步：' -ForegroundColor Green
Write-Host '  1. 完全退出并重启 DeepSeek Harness（skill 与截图工具需重启后生效）'
Write-Host '  2. 开启截图监控：双击 ~\.dsh\tools\screenshot-tool\start-screenshot-autosave.bat'
Write-Host '  3. 之后按 Win+Shift+S 截图会自动存盘，粘贴出的是图片路径'
