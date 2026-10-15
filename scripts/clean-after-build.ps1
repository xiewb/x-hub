# x-hub 构建打包后的自动清理脚本
# 触发：npm run tauri:build 打包完成后，由 package.json 的 posttauri:build 自动调用
# 目标：释放磁盘空间，同时保留"最新一次构建状态"，不影响下一次编译速度。
#
# 清理规则（全部只碰旧版本，最新状态原样保留）：
#   1) 增量编译缓存（incremental/）：每个 crate 只保留最新一个会话目录，删除其余历史会话。
#      —— 最新会话就是"下一次编译的进度"（实测 app_lib 曾有 20 个会话 11.5 GB，
#         其中 19 个旧会话 10.8 GB 是纯垃圾）；历史会话删除后 cargo 会按需重建，零风险。
#   2) deps/build 旧版本产物：cargo sweep --maxsize 从最旧的产物开始裁剪，保留最近使用的缓存。
#      —— $MaxSize 是 target 目录裁剪上限（不含保留的增量会话）：
#         调小 = 更省空间（下次编译稍慢）；调大 = 编译更快（占盘更多）。默认 10GB。

param(
    [string]$MaxSize = "10GB"
)

$ErrorActionPreference = "Continue"
$srcTauri = Join-Path $PSScriptRoot "..\src-tauri"

function Get-DirSizeGB([string]$Path) {
    if (-not (Test-Path $Path)) { return 0 }
    $o = robocopy $Path NULL /L /S /BYTES /NJH /NFL /NDL /NP 2>$null | Out-String
    $m = [regex]::Match($o, "Bytes\s*:\s*([\d\.]+)\s*[kMG]?")
    if ($m.Success) { return ([double]$m.Groups[1].Value) / 1GB }
    return 0
}

$target = Join-Path $srcTauri "target"
if (-not (Test-Path $target)) {
    Write-Host "[clean] 未找到 $target，跳过"
    exit 0
}

$before = Get-DirSizeGB $target
Write-Host "[clean] 清理前 target: $([math]::Round($before,2)) GB"

# ---- 1) 剪掉每个 crate 的旧增量会话，只保留最新一个 ----
foreach ($profile in @("debug", "release")) {
    $inc = Join-Path $target "$profile\incremental"
    if (-not (Test-Path $inc)) { continue }
    $removed = 0
    Get-ChildItem $inc -Directory -ErrorAction SilentlyContinue |
        Group-Object {
            $i = $_.Name.LastIndexOf('-')
            if ($i -gt 0) { $_.Name.Substring(0, $i) } else { $_.Name }
        } |
        ForEach-Object {
            $newest = $_.Group | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            foreach ($d in ($_.Group | Where-Object { $_.FullName -ne $newest.FullName })) {
                Remove-Item -Recurse -Force $d.FullName -ErrorAction SilentlyContinue
                if (-not (Test-Path $d.FullName)) { $removed++ }
            }
        }
    if ($removed -gt 0) { Write-Host "[clean] $profile/incremental: 清理 $removed 个旧会话（已保留每个 crate 的最新会话）" }
}

# ---- 2) deps/build 旧版本产物：从最旧开始裁剪到 $MaxSize ----
if (Get-Command cargo-sweep -ErrorAction SilentlyContinue) {
    Push-Location $srcTauri
    cargo sweep --maxsize $MaxSize 2>&1 | ForEach-Object { Write-Host $_ }
    Pop-Location
} else {
    Write-Host "[clean] 未安装 cargo-sweep（cargo install cargo-sweep），跳过 deps 裁剪"
}

$after = Get-DirSizeGB $target
Write-Host "[clean] 清理后 target: $([math]::Round($after,2)) GB，本次释放 $([math]::Round($before - $after,2)) GB"
