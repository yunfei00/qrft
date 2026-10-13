# UA-011：Windows 11 真实 MP4 单机解码验收指南

**当前结果：2026-10-13 用户在 ChatGPT 会话中反馈本指南验收全部通过（UA-011 PASS）。** 这是用户报告的现场结论，并非 Codex 独立核对过该次录像、截图、日志和哈希原文；记录见 [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md)。**此指南保留用于后续问题复现，当前不需要再执行。**

**验收目标：** 使用 P8 已经保存的原始文件、第一段.mp4、补传段.mp4，验证新的 Decoder GUI 完成“首段识别 → 缺包 → 保存重开 → 补传合并 → 文件恢复 → MD5/SHA256 一致”。不重新编码、不重新录屏；不用重跑 Codex 已通过的 211 项 pytest、27 项 GUI 自动化、Ruff 和 CI。

**运行范围：** Windows 11、Python 3.12 + uv 源码运行；只用单机模式、1 个 Worker。单机可完成文件恢复；双 Windows / SMB 和大文件性能不在本轮。遇到错误立即停止，保留录像、数据库和日志，向开发者反馈，不要从头重复操作。

## 验收标准

| 编号 | 验证点 | 通过标准 |
| --- | --- | --- |
| U1 | 启动与工作区 | GUI 显示工作区已打开，无口令和额外服务启动命令 |
| U2 | 首段视频 | 识别 START，总包数 47；只传 DATA 0～9，所以有缺包且未恢复 |
| U3 | 缺包导出 | missing.txt、missing.csv、missing.json 生成，TXT 非空 |
| U4 | 停止与重启 | 重开相同工作区，旧任务/视频/已收包/缺包依旧存在 |
| U5 | 补传与恢复 | 同一任务导入补传视频；总包 47、已收 47、缺包 0、冲突 0，显示恢复成功 |
| U6 | 文件校验 | 恢复文件大小、MD5、SHA256 与原文件完全一致 |

实际首段漏识别时，缺包可能多于 37，不能直接算故障；但总包数必须能从 START 识别为 47。视频扫描到 100% 不等于文件恢复成功。

## 第 1 步：同步分支与依赖

打开普通 **PowerShell**。以下与 P8 一致使用 D:\code_2026\qrft。如果本地有未提交改动必须先停止，不要 reset、clean 或强推。将下面整个代码块复制执行：

~~~powershell
$ErrorActionPreference = 'Stop'
$repo = 'D:\code_2026\qrft'
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    throw "仓库不存在：$repo"
}
Set-Location $repo
if (git status --porcelain) {
    throw '工作区存在未提交修改，请先反馈，不能覆盖'
}
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'git fetch 失败' }
git switch feature/qrft-v2-hex-md5
if ($LASTEXITCODE -ne 0) { throw 'git switch 失败' }
git pull --ff-only origin feature/qrft-v2-hex-md5
if ($LASTEXITCODE -ne 0) { throw 'git pull 失败' }
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw 'uv sync 失败' }
$commit = (git rev-parse HEAD).Trim()
Write-Host "本轮 Commit: $commit"
~~~

**通过标准：** 同步无错误，能打印本轮 Commit。软件代码不应因这次验收而被手工修改。

## 第 2 步：找到 P8 已经成功使用的三个文件

先列出 P8 测试目录，找到之前成功的那一个：

~~~powershell
$testRoot = Join-Path $repo 'temp'
Get-ChildItem -LiteralPath $testRoot -Directory -Filter 'manual-v2-uv-*' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 10 FullName, LastWriteTime
~~~

从输出复制真实目录，把下面第一行的示例路径替换成它。若 P8 已移动到别处，可以改成真实路径，不用重录。

~~~powershell
$caseDir = 'D:\code_2026\qrft\temp\manual-v2-uv-请替换为真实目录'
$source = Join-Path $caseDir '测试文件,全部字节.bin'
$firstMp4 = Join-Path $caseDir '第一段.mp4'
$repairMp4 = Join-Path $caseDir '补传段.mp4'
foreach ($file in @($source, $firstMp4, $repairMp4)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "找不到文件，请检查 P8 真实保存位置：$file"
    }
}
Get-Item -LiteralPath $source, $firstMp4, $repairMp4 |
    Select-Object Name, Length, FullName
if ((Get-Item -LiteralPath $source).Length -ne 65536) {
    throw '选中的原文件不是 P8 的 64 KiB 测试样本，请核对目录'
}
Write-Host "原文件 MD5: $((Get-FileHash -LiteralPath $source -Algorithm MD5).Hash)"
~~~

**通过标准：** 原文件恰好 65536 字节，两个 MP4 均存在。**保留这三个文件原样不动**。若找不到任何一个，先反馈缺失文件及目录，不要求重新录屏。

## 第 3 步：新建独立工作区，启动 GUI

仍在同一个 PowerShell 中执行。命令会在仓库外新建专用工作区，不影响以前的恢复任务。

~~~powershell
$workspace = Join-Path (Split-Path -Parent $repo) ('qrft-decoder-field-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $workspace) { throw '本次目录已存在，请重新生成名称' }
New-Item -ItemType Directory -Path $workspace | Out-Null
$exportDir = Join-Path $workspace 'missing-export'
New-Item -ItemType Directory -Path $exportDir | Out-Null
Write-Host "本次工作区：$workspace"
uv run --no-sync python -m qrft.decoder_gui.main --workspace $workspace
~~~

在 GUI 的 **设置** 页，检查：运行方式“单机模式（自动启动本地服务）”、采样 FPS 60、Worker 数 1、时间片 30 秒。通常程序会**自动连接工作区**并切到“任务与恢复”。若未连接，可返回“设置”点击一次 **打开工作区 / 连接服务器**。

**通过标准：** 正常显示“工作区已打开”且 GUI 可操作；无须输入编码 CLI 口令 qsnfj、API Token，也无须单独启动 Control / Worker。Control 在连接工作区时启动，**本地 Worker 在点击“开始 / 继续”之后才启动**。

## 第 4 步：只导入第一段 MP4，检查缺包

在 **任务与恢复** 页：

1. 点击 **新建任务**，名称填 **P9-真实MP4验证**；接下来协议选择 **v2**。记下“当前任务”下拉框中的编号（#数字）。
2. 点击 **添加视频 / 同任务补传 MP4、AVI**，**只选择第一段.mp4**，来源确认框点击“是”。这一步不要同时导入补传段。
3. 视频列表出现首段路径和时长后，点击 **开始 / 继续**。等待此短视频扫描完成。窗口应仍然可以切换“节点与时间片”“实时日志”。
4. 观察“总包数、已验证包、缺包、重复、冲突”和扫描进度：正常应有总包数 47、至少 37 个缺包，当前不能恢复。首段实际识别的包数可能少于 10。
5. 点击 **导出缺包 TXT / CSV / JSON**，在文件夹选择框选择第 3 步创建的 **missing-export** 目录。只导出一次，以免同名文件拒绝覆盖。

**通过标准：** START 被识别，总包数 47；首段扫描结束，有缺包；missing-export 下同时存在 missing.txt、missing.csv、missing.json，且 TXT 非空。包号必须在 00000000 至 00000046 范围内。此时出现“待补传”不是失败。

**若一直等待 START、扫描失败、缺包报告为空/导出失败或 GUI 无响应，立即停止并反馈错误，不要先导入补传掩盖问题。**

## 第 5 步：停止、关闭、重开并确认持久化

首段扫描和缺包导出完成后：

1. 点击 **停止并保存**，等待状态显示“已暂停 / 停止，数据已保存”。
2. 点击 GUI 右上角 **X** 正常关闭，等待进程结束；**不要关闭当前 PowerShell**。
3. 回到原 PowerShell，用原有工作区路径重新启动：

~~~powershell
uv run --no-sync python -m qrft.decoder_gui.main --workspace $workspace
~~~

4. GUI 自动重连后，在“当前任务”选择刚才的 **P9-真实MP4验证**；确认首段视频仍在列表中，总包数 47、已识别数据包未归零、缺包统计没有丢失。

**通过标准：** 工作区、任务、视频、包数据持久化；不用重新扫描第一段。若丢失，停止并反馈日志。

## 第 6 步：导入补传 MP4，恢复文件

**继续在原任务内操作，不要新建任务。**

1. 点击 **添加视频 / 同任务补传 MP4、AVI**，只选择 **补传段.mp4**，确认来源与同一原文件一致。
2. 视频列表应显示首段和补传两行。点击 **开始 / 继续**，等待补传段扫描完成。
3. 观察数据包：**总包 47、已验证包 47、缺包 0、冲突 0**。
4. 正常应自动显示“恢复成功：数据完整且文件哈希匹配”。若包已齐但暂未恢复，点击 **校验并恢复文件** 一次即可。若报错则先反馈，不反复点击。
5. 点击 **打开结果目录**，确认文件确实存在。

**通过标准：** 恢复成功，显示正确哈希，没有覆盖用户原文件。若仍有缺包就保留任务和录像，先反馈缺包结果，不立刻重录。

## 第 7 步：对比文件大小、MD5、SHA256

GUI 恢复成功后先正常关闭窗口，回到同一个 PowerShell（前面变量还在）：

~~~powershell
$outputRoot = Join-Path $workspace '.qrft-decoder\outputs'
if (-not (Test-Path -LiteralPath $outputRoot)) { throw "恢复目录不存在：$outputRoot" }
$sourceName = Split-Path -Leaf $source
$matches = @(
    Get-ChildItem -LiteralPath $outputRoot -Recurse -File |
    Where-Object { $_.Name -eq $sourceName -and $_.Directory.Name -eq 'files' }
)
if ($matches.Count -ne 1) {
    throw "找到 $($matches.Count) 个匹配恢复文件，预期恰好 1 个；请核对结果目录"
}
$restored = $matches[0].FullName
$originalSize = (Get-Item -LiteralPath $source).Length
$restoredSize = (Get-Item -LiteralPath $restored).Length
$originalMd5 = (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash
$restoredMd5 = (Get-FileHash -LiteralPath $restored -Algorithm MD5).Hash
$originalSha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$restoredSha = (Get-FileHash -LiteralPath $restored -Algorithm SHA256).Hash
Write-Host "原始文件：$source"
Write-Host "恢复文件：$restored"
Write-Host "大小：$originalSize / $restoredSize"
Write-Host "MD5：$originalMd5 / $restoredMd5"
Write-Host "SHA256：$originalSha / $restoredSha"
if ($originalSize -ne $restoredSize -or
    $originalMd5 -ne $restoredMd5 -or
    $originalSha -ne $restoredSha) {
    throw '验收失败：原始与恢复文件不一致'
}
Write-Host 'UA-011 实际 MP4 GUI 恢复验收：PASS'
~~~

**通过标准：** 大小 65536 / 65536，MD5 与 SHA256 分别一致，输出 **UA-011 实际 MP4 GUI 恢复验收：PASS**。

## 第 8 步：反馈结果和错误（不要重复做已通过的步骤）

**通过时：** 回复 **UA-011 PASS**，建议附恢复成功的 GUI 截图、第 7 步 PowerShell 输出。

**失败时：** 立即停在当前步骤，不删除任何测试文件、工作区、数据库、日志，也不重新编码/录屏。反馈以下信息：

~~~text
UA-011 FAIL
失败步骤：第 N 步（U1-U6）
实际操作：点击了什么按钮 / 输入了什么
实际结果：错误提示、界面状态、是否卡住
预期结果：本手册的对应通过条件
Commit：第 1 步打印的 Commit
任务编号：#...
工作区：第 3 步打印的实际路径
附件：GUI 截图；PowerShell 末尾错误；必要时实时日志末尾内容
~~~

日志在 **工作区\.qrft-decoder\logs** 下，通常包括 control-*.log 和 desktop-*.log。反馈前请遮盖个人文件路径、Token 和不便公开的数据；不用上传原始文件和 MP4 到公共 GitHub。开发者修复后**只复测失败步骤及受影响的关联流程**，不从头验收全部功能。

## 不在本轮重复的内容

- P8 编码、二维码播放、Windows 录屏、CLI 口令不需要再次验证。
- 211 项 pytest、Ruff、CI、27 项 Codex 自动 GUI 检查不需要人工重跑。
- 单机多个 Worker、503、租约重领、任务取消和异常帧已自动验证；短视频不适合用户手动捕捉暂停中的瞬时状态。
- 真实双 Windows/SMB、物理断网重连未验收；**不影响本轮单机**判定。
- 1 GB 全二维码传输、长视频性能和 30/60 分钟稳定性是独立的压力验收项目。64 KiB 真录屏恢复成功不等于大文件性能通过。

更多信息：[UA-011 总入口](USER_ACTIONS.md)、[解码手册](DECODER_USER_GUIDE.md)、[自动验收结果](ACCEPTANCE_RESULTS.md)、[P8 已验收的编码说明](V2_USER_GUIDE.md)。
