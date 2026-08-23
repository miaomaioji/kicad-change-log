# 向 KiCad 官方元数据仓库提交插件(一键脚本)
#
# 前置条件(仅需一次):
#   1. 安装 glab CLI(见下方注释)
#   2. 登录 GitLab: glab auth login --hostname gitlab.com --device
#      在浏览器打开 https://gitlab.com/oauth/device 输入一次性代码并授权
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File tools\submit_to_gitlab.ps1
#
# 脚本会:fork kicad/addons/metadata → 推送
# packages/com.github.miaomaioji.kicad-change-log/metadata.json → 创建 MR

param(
    [string]$MetadataPath = "",  # 默认使用仓库内 submit\metadata.json(与 Release zip 匹配)
    [string]$Branch = ""         # 默认 add-kicad-change-log-v<版本>
)

$ErrorActionPreference = "Stop"

$IDENTIFIER = "com.github.miaomaioji.kicad-change-log"
$UPSTREAM = "kicad/addons/metadata"
$TARGET_BRANCH = "main"

$RepoRoot = Split-Path -Parent $PSScriptRoot

# --- 1. 定位 metadata.json ---
if (-not $MetadataPath) {
    $candidates = @(
        (Join-Path $RepoRoot "submit\metadata.json"),
        (Join-Path $RepoRoot "dist\metadata.json")
    )
    $MetadataPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $MetadataPath -or -not (Test-Path $MetadataPath)) {
    Write-Error "未找到 metadata.json。请先运行 build_pcm.py,或从 GitHub Release 下载 metadata.json 资产。"
    exit 1
}
$meta = Get-Content $MetadataPath -Raw | ConvertFrom-Json
if ($meta.identifier -ne $IDENTIFIER) {
    Write-Error "metadata.json 的 identifier 不是 $IDENTIFIER"
    exit 1
}
$version = $meta.versions[0].version
if (-not $Branch) { $Branch = "add-kicad-change-log-v$version" }

# --- 2. 定位 glab ---
$glab = Get-Command glab.exe -ErrorAction SilentlyContinue
if ($glab) { $glab = $glab.Source } else {
    $local = Join-Path $env:LOCALAPPDATA "glab\bin\glab.exe"
    if (Test-Path $local) { $glab = $local } else {
        Write-Error @"
未找到 glab CLI。安装方法:

  Invoke-WebRequest -Uri 'https://gitlab.com/api/v4/projects/gitlab-org%2Fcli/packages/generic/glab/1%2E114%2E0/glab_1%2E114%2E0_windows_amd64%2Ezip' -OutFile "$env:TEMP\glab.zip"
  Expand-Archive "$env:TEMP\glab.zip" "$env:LOCALAPPDATA\glab" -Force

"@
        exit 1
    }
}

# --- 3. 检查登录 ---
& $glab auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "glab 未登录。请先运行: glab auth login --hostname gitlab.com --device"
    exit 1
}
$username = (& $glab api user | ConvertFrom-Json).username
$forkPath = "$username/metadata"
Write-Host "当前 GitLab 用户: $username"

# --- 4. fork 上游仓库 ---
Write-Host "fork $UPSTREAM ..."
try {
    & $glab api --method POST "projects/kicad%2Faddons%2Fmetadata/fork" *> $null
} catch {
    Write-Host "fork 请求返回错误(可能已 fork 过),继续..."
}
$ready = $false
for ($i = 0; $i -lt 10; $i++) {
    & $glab api "projects/$([uri]::EscapeDataString($forkPath))" *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 3
}
if (-not $ready) {
    Write-Error "fork 未就绪,请稍后重试或检查网络。"
    exit 1
}
Write-Host "fork 就绪: $forkPath"

# --- 5. 准备分支并推送 ---
$work = Join-Path $env:TEMP ("kicad-metadata-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
git clone --depth 1 "https://gitlab.com/$forkPath.git" $work
Push-Location $work
git checkout -b $Branch

$pkgDir = Join-Path $work ("packages\" + $IDENTIFIER)
New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null
Copy-Item $MetadataPath (Join-Path $pkgDir "metadata.json") -Force
git add -A
git commit -m "Add $IDENTIFIER (v$version)"
git push -u origin $Branch
Pop-Location
Write-Host "已推送到分支: ${forkPath}:${Branch}"

# --- 6. 创建 MR ---
Write-Host "创建合并请求..."
& $glab mr create --repo $UPSTREAM `
    --source-branch $Branch --target-branch $TARGET_BRANCH `
    --title "Add $IDENTIFIER (v$version)" `
    --description "提交插件包 **$($meta.name)** 到官方仓库。``n``n- 源码: https://github.com/miaomaioji/kicad-change-log``n- 许可证: MIT``n- 下载: $($meta.versions[0].download_url)" `
    --yes
if ($LASTEXITCODE -eq 0) {
    Write-Host "MR 创建成功!可在 https://gitlab.com/kicad/addons/metadata/-/merge_requests 查看。"
} else {
    Write-Error "MR 创建失败(可能已存在同名 MR)。请手动打开: https://gitlab.com/$forkPath/-/merge_requests/new"
    exit 1
}
