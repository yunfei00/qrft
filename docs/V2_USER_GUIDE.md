# QRFT v2 中文操作与 Windows 11 真实录屏验收

v2-P9 已增加统一源码解码 GUI，单机无需手动启动 Control/Worker；新桌面操作按 [DECODER_USER_GUIDE.md](DECODER_USER_GUIDE.md) 和 UA-011。下方 P8 第 1～10 步保留已验收的编码/CLI 操作与历史证据，不要求重复执行。

日期：2026-10-12。本分支 feature/qrft-v2-hex-md5 的软件版本为 0.4.0.dev0，尚未合并 main、未发布 Release。**当前推荐使用下文“Windows 11 本地源码验收（uv）”**，直接从本分支运行 Python 源码，不使用打包 EXE。后面的 EXE 流程保留作历史参考。协议参数见 PROTOCOL.md。

**v2-P8 状态：第 1～10 步已由用户在 Windows 11 报告全部 PASS。** [人工验收记录及证据边界](ACCEPTANCE_RESULTS.md) 明确区分用户反馈与 Codex 自动测试；录屏路径、哈希数值、FPS/DPI、日志/截图未提供。用户无需重复已完成的验收。操作索引以 [USER_ACTIONS.md 的 UA-010 / UA-009](USER_ACTIONS.md) 为准，本章是详细执行入口。

## Windows 11 本地源码验收（uv）

在同一个 PowerShell 窗口依次执行以下代码块。示例工作区为 D:\code_2026\qrft；如仓库位于其他位置，只需修改第一块中的 $repo。切换前检查工作区是否干净，发现未提交修改即停止，不会覆盖或清理它们。自动生成的测试数据放在 Git 忽略的 temp 子目录。

### 1. 获取并切换开发分支

首次运行会克隆指定分支；已有工作区会检查本地修改、获取远端并快进更新。验收条件是当前分支为 feature/qrft-v2-hex-md5 且 git status --short 无输出。网络或 Git 错误先修复后重跑；检测到本地修改时先自行备份或提交，命令会停止保护这些内容。

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'D:\code_2026\qrft'
$branch = 'feature/qrft-v2-hex-md5'
$remote = 'https://github.com/yunfei00/qrft.git'
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    if (Test-Path -LiteralPath $repo) { throw "目录已存在但不是Git工作区，请修改 repo 路径：$repo" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $repo) -Force | Out-Null
    git clone --single-branch --branch $branch $remote $repo
    if ($LASTEXITCODE -ne 0) { throw 'git clone 失败' }
} else {
    if (git -C $repo status --porcelain) { throw "工作区有修改，为保护文件已停止：$repo" }
    git -C $repo fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'git fetch 失败' }
    if (git -C $repo branch --list $branch) {
        git -C $repo switch $branch
    } else {
        git -C $repo switch --track -c $branch "origin/$branch"
    }
    if ($LASTEXITCODE -ne 0) { throw "切换到 $branch 失败" }
    git -C $repo pull --ff-only origin $branch
    if ($LASTEXITCODE -ne 0) { throw '快进同步失败' }
}
Set-Location $repo
if ((git branch --show-current) -ne $branch) { throw "当前分支不是 $branch" }
git status --short
git log -1 --oneline
```

### 2. 安装 Python 3.12 并同步 uv 依赖

项目使用 encoder、GUI、decoder、control、acceptance 全部 extras 及 dev 测试组。通过条件是 Python 显示 3.12.x，且 OpenCV、qrcode、ZXing、PySide6 均可导入。下载或导入失败时检查网络/索引并重试；不要删除或手工改写 uv.lock。

```powershell
Set-Location $repo
uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'uv Python 3.12 安装失败' }
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw 'uv 依赖同步失败' }
uv run --no-sync python --version
if ($LASTEXITCODE -ne 0) { throw 'Python 环境启动失败' }
uv run --no-sync python -c "import cv2, qrcode, zxingcpp, PySide6; print('核心依赖导入成功')"
if ($LASTEXITCODE -ne 0) { throw '依赖导入失败，请重跑 uv sync' }
```

### 3. 验证源码模块入口和实际参数

实际入口是 qrft.encoder_gui.main、qrft.encoder_cli.entrypoint 和 qrft.decoder.entrypoint。GUI 与 Decoder 帮助保持原样；编码 CLI 不提供 -h/--help。运行下面的编码 CLI 后，终端会静默等待；直接输入大小写敏感的 `qsnfj` 并按回车（输入隐藏），正确后才显示操作菜单。最多三次；错误时不编码、不写文件、不打开播放器。必须在普通交互式 PowerShell/Windows Terminal 运行，不支持管道、重定向、环境变量或参数传入口令。这是本地操作入口校验，不是安全授权或防逆向机制。命令失败时确认工作目录及依赖。

静默等待并不是卡死：此时没有口令提示文字，也不会显示输入字符或星号。请手动输入小写 `qsnfj` 后按 **Enter**，不要输入引号、前后空格或命令本身；GUI 入口完全不需要这一步。三次错误后本次 CLI 调用非零退出，可在同一交互式 PowerShell 重新执行同条命令，再手动输入；重启 CLI 会重新校验，不需要重建样本或更改协议。已记录用户第 6 步三次失败后重新手动输入成功的经过，未推断最初失败原因。

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder_gui.main --help
if ($LASTEXITCODE -ne 0) { throw 'GUI 源码入口失败' }
uv run --no-sync python -m qrft.encoder_cli.entrypoint
if ($LASTEXITCODE -ne 0) { throw '编码器/OpenCV 源码入口失败' }
uv run --no-sync python -m qrft.decoder.entrypoint --help
if ($LASTEXITCODE -ne 0) { throw 'Decoder 源码入口失败' }
```

### 4. 创建二进制样本和本次任务路径

样本大小 65536 字节，内容循环覆盖 00–FF，中文逗号文件名；按 1400 字节分块共 47 包，末包保留实际长度。唯一目录不会覆盖已有文件。后续命令在此 PowerShell 窗口执行，以保留已定义变量。

```powershell
Set-Location $repo
$work = Join-Path $repo (Join-Path 'temp' ('manual-v2-uv-' + [guid]::NewGuid().ToString('N')))
New-Item -ItemType Directory -Path $work | Out-Null
$source = Join-Path $work '测试文件,全部字节.bin'
$partialMp4 = Join-Path $work '第一段.mp4'
$repairMp4 = Join-Path $work '补传段.mp4'
$task = Join-Path $work '恢复任务'
$sample = [byte[]]::new(65536)
for ($i = 0; $i -lt $sample.Length; $i++) { $sample[$i] = [byte]($i % 256) }
[System.IO.File]::WriteAllBytes($source, $sample)
$sourceMd5 = (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash
Get-Item -LiteralPath $source | Select-Object FullName, Length
Write-Output "原始MD5：$sourceMd5；预期数据包数：47"
```

若文件大小或包数不符，停止并创建新样本。通过条件是大小 65536 字节并记下源 MD5。

### 5. 启动源码 v2 GUI 编码器

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder_gui.main
if ($LASTEXITCODE -ne 0) { throw 'GUI 编码器退出失败' }
```

GUI 不需要口令。在 GUI 选择第 4 步输出的源文件，选择“v2 HEX + MD5”，点击“检查文件”。预期总块数 47、文件 MD5 与上一步一致，v2 参数锁定 1400 字节、50 ms、L/10/4。普通传输留空补传清单；补传时选择同一任务的 missing.txt。PNG 导出先选新建的输出目录，不能覆盖已有 PNG。后台检查和导出显示任务进度，可点“取消任务”。较小屏幕可滚动查看所有设置。

若直接用 GUI 录屏，保持全屏复选框未勾选，点击“准备二维码”：Qt 播放器显示首个 START 后一直静止等待。录像开始后点播放器使其获得焦点，按 Space 开始；Space 暂停/继续，Esc 结束（全屏下也直接结束），F11 可在录制前切换全屏。提示和进度均在二维码白色正方形之外。录制期间不得移动窗口、切换屏幕/全屏或改变 DPI。本文后续使用 OpenCV，请先关闭 Qt 播放器及 GUI，避免同时出现多个二维码。通过条件是固定参数、正确哈希、首帧等待和按键行为正确；无法启动/裁切时检查依赖、桌面和屏幕空间。

### 6. OpenCV 播放并用 Windows 11 截图工具录制第一段 MP4

先打开 Windows 11 截图工具录像功能。运行下面命令，在静默终端输入口令并回车。默认是固定大小的非全屏窗口；首次二维码准备好后立即显示并无限等待 Space，不倒计时、不自动开始。此段只发 DATA 0–9，稳定产生缺包；START/FINISH 仍各 20 次、50 ms，DATA 默认每包一次、50 ms。

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder_cli.entrypoint play $source --protocol v2 --player opencv --start-id 0 --end-id 9
$playExit = $LASTEXITCODE
if ($playExit -eq 130) {
    Write-Warning '播放器提前退出；请独立检查截图工具是否保存 MP4，再决定解码或重新录制。'
} elseif ($playExit -ne 0) {
    throw 'CLI 校验、参数或播放失败；查看终端信息，口令错误时重新执行并手动输入。'
}
```

按 Win+Shift+R 或打开截图工具→录像→新建，**框选标题提示下的整个固定白色正方形（926×926 物理像素），不要仅框选最初较小的 START**。窗口正常传输/补传布局相同，二维码在白色区域内居中，位置不会随帧变化；留白包含完整静区，文字在区域外。点击截图工具“开始”，等待其录像倒计时结束，再点击播放器窗口获得键盘焦点并短按 Space。长按不应连续切换，Space 可暂停/继续，Esc 可提前取消。完成后播放器保留最后一帧并在区域外显示 FINISHED；先停止录制，再按 Esc 正常结束（退出码 0；未完成时 Esc/关闭退出码 130）。把原始 MP4 保存为第 4 步打印的 work 路径下第一段.mp4。不要裁剪、缩放、拖动窗口或编辑录像。

可在命令末尾加 --fullscreen 使用可选全屏，但必须在框选前选择；默认不全屏。旧 --initial-delay-ms 仅保留参数兼容，不再自动倒计时。焦点不在播放器时按键不会生效，请先点击播放器。窗口关闭与 Esc 均结束自有播放器。出现裁切/容量/空间不足、按键无效或无 MP4 即失败；请更换足够大的显示区域并重新录制，不能改 1400 字节或缩小二维码来宣称通过。

**播放退出与录像保存是两个独立结果。** 上述 OpenCV 命令播放完成后 Esc/关闭返回 0，未完成时 Esc/关闭返回 130；校验或其他错误也会非零退出。播放器不负责保存 MP4，保存操作由截图工具完成。130 不证明 MP4 不存在或损坏，0 也不证明截图工具已保存；必须检查 `$partialMp4` 是否存在并按第 7 步解码。完整白色区域、START 和所需 DATA 是否被录到，最终以实际解码/缺包结果判断。这里的 130 说明仅针对 OpenCV CLI，不能套用于 Qt GUI 的进程退出码。

### 7. 从源码解码第一段并检查 missing.txt

```powershell
Set-Location $repo
if (-not (Test-Path -LiteralPath $partialMp4)) { throw "找不到录像：$partialMp4" }
uv run --no-sync python -m qrft.decoder.entrypoint $partialMp4 --protocol v2 --sample-fps 60 --output $task
$decodeExit = $LASTEXITCODE
if ($decodeExit -notin @(0, 2)) { throw "源码 Decoder 失败，退出码：$decodeExit" }
if ($decodeExit -ne 2) { throw '第一段意外完整；请用新 work 重做首段，保留仅发包0–9的范围' }
$missing = Join-Path $task 'missing.txt'
if (-not (Test-Path -LiteralPath $missing)) { throw '缺少 missing.txt；检查录像是否捕获 START' }
$missingIds = @(Get-Content -LiteralPath $missing | Where-Object { $_.Trim() })
Get-Content -LiteralPath $missing
Write-Output "缺包数：$($missingIds.Count)；任务目录：$task"
```

预期退出码 2（数据不全），任务数据库保留已识别帧，missing.txt 非空，至少包含 00000010–00000046；额外录屏漏帧也会列入。没有 START 或清单为空时用新 work 重做第 6 步。通过条件是缺包编号都在 0–46 且没有发布恢复文件。

### 8. 用缺包清单生成补传二维码并录制

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder_cli.entrypoint play $source --protocol v2 --player opencv --retransmit $missing
$playExit = $LASTEXITCODE
if ($playExit -eq 130) {
    Write-Warning '补传播放器提前退出；检查截图工具保存的 MP4，缺包仍可继续补传。'
} elseif ($playExit -ne 0) {
    throw '补传 CLI 校验、参数或播放失败；查看终端信息并重新执行。'
}
```

本次再次在终端输入口令。补传窗口同样显示首帧并静止等待，按第 6 步框选相同白色正方形，先启动截图工具录制、再点击播放器并按 Space。完成后停止录制、保存 work 下补传段.mp4，再按 Esc。编码器读取 missing.txt，保持未改变的源文件、1400 字节分块和原包号。正常完整播放预期退出码 0 且 MP4 已保存；若提前退出为 130，按第 6 步独立检查保存文件并在第 9 步验证，补传是否足够以缺包及恢复 MD5 结果判断。其他文件、清单、校验或播放错误按终端信息排查，不更改源文件或任务。

### 9. 将补传视频导入同一任务并核对 MD5

```powershell
Set-Location $repo
if (-not (Test-Path -LiteralPath $repairMp4)) { throw "找不到补传录像：$repairMp4" }
uv run --no-sync python -m qrft.decoder.entrypoint $repairMp4 --protocol v2 --sample-fps 60 --output $task
if ($LASTEXITCODE -ne 0) { throw "补传未完成；检查 $task\\missing.txt 后继续第 8 步" }
$restored = Join-Path (Join-Path $task 'files') ([System.IO.Path]::GetFileName($source))
if (-not (Test-Path -LiteralPath $restored)) { throw "恢复文件不存在：$restored" }
$restoredMd5 = (Get-FileHash -LiteralPath $restored -Algorithm MD5).Hash
Write-Output "原始 MD5：$sourceMd5"
Write-Output "恢复 MD5：$restoredMd5"
if ($restoredMd5 -ne $sourceMd5) { throw 'MD5 不一致；保留本次 work 和日志，验收失败' }
Get-Content -LiteralPath (Join-Path $task 'verification.json') -Encoding UTF8
Write-Output 'PASS：源码编码、录屏、缺包、补传、合并及MD5校验成功。'
```

通过条件是退出码 0、恢复文件位于 task 下 files 子目录、missing.txt 为空、verification.json 状态为 verified 且两项 MD5 一致。仍有缺包时可用更新后的同一清单重复第 8–9 步；MD5 不同或数据包冲突时停止验收并保留独占 work 排查，不覆盖文件或导入不明来源视频。

自动测试覆盖源码二维码和 AVI 视频链路，本地自动测试不等于截图工具 MP4 录制。本次真实 Windows 11 MP4 及第 1～10 步的 PASS 来自用户反馈，见 ACCEPTANCE_RESULTS.md；Codex 未直接查阅其录像或文件。后续需要复现时可按 UA-009 保留环境/日志证据，不要求用户重复已经报告成功的流程。

### 10. 独立纯 CLI 导出 PNG（不初始化 GUI）

下面代码块可单独在新 PowerShell 窗口执行；输入真实文件的完整路径。每次 CLI 调用在静默阶段输入上述口令，再执行 export。输出是 PNG 序列与 manifest.json，采用独占新目录，终端随后显示 JSON 结果，不打开 GUI/播放器。不使用 -h/--help；未知/缺失参数在校验之后返回非零且不显示 usage。

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'D:\code_2026\qrft'
Set-Location $repo
$source = Read-Host '输入待编码文件的完整路径'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw '源文件不存在' }
$png = Join-Path $repo ('temp\v2-png-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync python -m qrft.encoder_cli.entrypoint export $source --protocol v2 --output $png
if ($LASTEXITCODE -ne 0) { throw '编码失败；查看终端信息，不要覆盖已有目录重试' }
Get-Content -LiteralPath (Join-Path $png 'manifest.json') -Encoding UTF8
Write-Output "PNG 输出目录：$png"
```

不带操作参数启动 CLI 只在校验后显示菜单，不会编码；export 才写文件，play 才打开播放器。v1 使用 --protocol v1，可继续配置 --chunk-size；v2 固定参数保持冻结。直接运行 qrft.encoder_cli.main 或 qrft.encoder_cli.player 也执行同样校验，GUI 内部共享编码函数不要求口令。

## Windows 11 EXE 录屏验收步骤（历史参考）

本节保留旧构建的倒计时/全屏操作记录。P8 开发源码和新构建以以上静止首帧、固定窗口、交互口令步骤为准，不要使用旧的自动开始步骤验收当前代码。

准备原生1080p及以上显示器、Windows11 更新后的“截图工具”。二维码数据区可能达到785×785或更大，必须录制整个固定播放区和四周留白，不只框选最初较小的 START。请关闭遮挡二维码的通知和光标提示；不使用视频裁剪、二次缩放或有损编辑。

1. **启动编码器**：完整构建中打开 `QRFT-Encoder-GUI/QRFT-Encoder-GUI.exe`。本机开发构建在 `D:\code_2026\qrft\temp\v2-build\dist`，也可以从本分支 CI 的五程序构件解压后启动。
2. **选择文件**：点击“选择文件”，选择任意原始二进制文件，记下完整路径。不要在传输或补传期间修改它。
3. **选择 v2**：协议选“v2 HEX + MD5”，点击“检查文件”。分块锁为1400、纠错L、模块10、边框4，播放默认50ms；MD5必须对应同一原文件。可先用下面的命令记录 MD5。
4. **开始播放**：设置开始延迟为10000ms，勾选全屏，点击“开始播放”。START/FINISH各20次、DATA各一次。空间不足时报错，请换更大显示区域，不能把1400改小来冒充指定协议。
5. **启动 Windows 自带录屏**：按 `Win+Shift+R`，或开始菜单打开“截图工具”→录像→新建。框选整个白色播放区（包含最宽DATA和四周留白），点击“开始”。首次START前应已进入录制；工具的录制倒计时需要包含在10秒准备时间内。GUI因准备二维码而延迟并不代表已开始发送，确认画面后再计时。
6. **保存 MP4**：显示播放完成后停止录制；在截图工具预览中保存原始录像为 MP4，不转换GIF或二次编辑。保存到下面的独占 `$work` 目录，例如 `第一次.mp4`。微软操作依据：[截图工具录屏说明](https://support.microsoft.com/en-gb/windows/apps/use-snipping-tool-to-capture-screenshots)。
7. **启动解码器**：Decoder 为无界面工具，使用下面的 PowerShell 命令；不要求在目标机安装 Python。
8. **选择视频**：下面命令弹出文件选择对话框选择已保存 MP4；视频显式关联 `$task` 这个恢复任务目录。扫描步幅向下取整，避免30fps录像请求20fps却只扫描15fps；默认60扫描常见录像的每一帧。不能将不明来源视频导入同一目录。
9. **查看缺包**：输出目录有 `missing.txt`、CSV、JSON；没有 START 时 `.qrft-session/status.json` 显示 awaiting_start，不能推断缺包。缺包时退出码2，不生成最终文件。
10. **恢复文件**：原始帧持久化到任务 SQLite；包齐且完整文件MD5一致才在 `$task\files` 生成文件，`verification.json` 记录 MD5/SHA256与状态。FINISH不是成功依据。已有目标文件不覆盖。
11. **验证 MD5**：使用 `Get-FileHash -Algorithm MD5` 比较原文件与恢复文件；结果必须一致。
12. **补传及合并**：保持源文件不变，在编码GUI选择同一文件/v2，导入该任务的 `missing.txt` 后再次播放、录制补传 MP4，再用同一个 `$task` 导入。也可以用下面的 CLI OpenCV 路径补传。不要新建任务目录，否则不能合并以前的已收包。

### 可复制的 PowerShell 命令

先配置开发构建根目录，选择原始文件并创建独占验收目录：

```powershell
$programs = 'D:\code_2026\qrft\temp\v2-build\dist' # 使用CI构件时改为完整解压根目录
Add-Type -AssemblyName System.Windows.Forms
$pick = New-Object System.Windows.Forms.OpenFileDialog
$pick.Title = '选择原始二进制文件'
if ($pick.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw '未选择文件' }
$source = $pick.FileName
$work = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('QRFT-v2-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$task = Join-Path $work '恢复任务'
Get-FileHash -LiteralPath $source -Algorithm MD5
```

符合指定要求的 **OpenCV** 播放路径（替代GUI第4步）：

```powershell
& "$programs\QRFT-Encoder-CLI\QRFT-Encoder-CLI.exe" play $source --protocol v2 --player opencv --initial-delay-ms 10000
```

固定926×926白色画布保持录制区域不变；画布内二维码仍为原图50%最近邻缩放，增加外部白色空间不会改变二维码模块/边框。空格暂停/继续，Esc停止。Qt默认播放器仍可用，GUI无需换框架。50ms为显示调度间隔，生成不足或Windows调度可能延长，不能从此推算真实传输速度。

选择并恢复第一次录屏：

```powershell
$pick.Title = '选择第一次录屏MP4'
$pick.Filter = '视频 (*.mp4;*.avi)|*.mp4;*.avi|所有文件 (*.*)|*.*'
if ($pick.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw '未选择录像' }
$video = $pick.FileName
& "$programs\QRFT-Decoder\QRFT-Decoder.exe" $video --protocol v2 --sample-fps 60 --output $task
# 退出码0表示恢复成功，2表示缺包/缺少START，其他非零为错误；查看控制台日志。
if (Test-Path -LiteralPath "$task\missing.txt") { Get-Content -LiteralPath "$task\missing.txt" }
if (Test-Path -LiteralPath "$task\verification.json") { Get-Content -LiteralPath "$task\verification.json" -Encoding UTF8 }
```

补传、录制第二次并导入同一目录：

```powershell
& "$programs\QRFT-Encoder-CLI\QRFT-Encoder-CLI.exe" play $source --protocol v2 --player opencv --retransmit "$task\missing.txt" --initial-delay-ms 10000
# 按同样录屏步骤保存补传MP4，再选择它。
$pick.Title = '选择补传录屏MP4'
if ($pick.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw '未选择补传录像' }
$repair = $pick.FileName
& "$programs\QRFT-Decoder\QRFT-Decoder.exe" $repair --protocol v2 --sample-fps 60 --output $task
# 或一次明确导入多个同文件视频到一个新任务：Decoder.exe $video $repair --protocol v2 --output 新目录
$restored = Join-Path (Join-Path $task 'files') ([System.IO.Path]::GetFileName($source))
$expected = (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash
$actual = (Get-FileHash -LiteralPath $restored -Algorithm MD5).Hash
if ($actual -ne $expected) { throw '原始与恢复MD5不一致' }
Write-Output "MD5一致：$actual"
```

若只缺 START，可不改变文件、播放范围选择开始/结束为同一已收包，补传视频再次携带START即可；已收DATA去重。空文件START总块数0，不发送DATA。重复完成恢复不会覆盖已有文件；完成后查看已有验证记录，不重复输出到同名路径。

## 控制中心与分布式 v2

用本分支 Control，Token置于 `QRFT_API_TOKEN` 环境变量，数据库/输出使用专用目录。在 Web 创建任务时选 v2；视频和补传视频都关联同一个task_id。原任务版本不能事后切换，旧任务保持v1。节点用新 Decoder：

每个控制中心/Worker的PowerShell会话都先执行以下初始化，输入同一验收Token，命令不会把Token打印或写入文件：

```powershell
$programs = 'D:\code_2026\qrft\temp\v2-build\dist'
$secureToken = Read-Host '输入本次验收Token（两端相同）' -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try { $env:QRFT_API_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer) }
```

控制中心会话使用独占数据库/输出目录，然后启动服务：

```powershell
$controlWork = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('QRFT-v2-control-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $controlWork | Out-Null
$env:QRFT_DB_PATH = Join-Path $controlWork 'control.sqlite3'
$env:QRFT_OUTPUT_DIR = Join-Path $controlWork '恢复文件'
& "$programs\QRFT-Control\QRFT-Control.exe" --host 127.0.0.1 --port 8787
```

另一个已执行相同Token初始化的会话启动Worker：

```powershell
& "$programs\QRFT-Decoder\QRFT-Decoder.exe" worker --server http://127.0.0.1:8787 --node-id Windows-A
```

本机用浏览器打开 `http://127.0.0.1:8787/`、输入同一Token，在任务下拉协议选择v2。真正第二台设备需控制中心改为 `--host 0.0.0.0`、只允许验收局域网访问8787端口，Worker的server改为控制机IP；Windows已有SMB登录会话应能读同一UNC视频。不能把Token写入公开JSON配置或日志。测试数据库/目录无需删除，保留用于追溯。

Web登记节点可直接访问的视频路径及真实时长。Worker默认60fps扫描，不要求每个时间片有START，HTTP批量保持原始v2帧。两台设备通过SMB读取同一视频仍需按UA-008做真实现场验收，不能以两个本地进程替代。MD5用于一致性检查，不是恶意篡改认证；Token鉴权不关闭。

## 判定与反馈

本次 v2-P8 第 1～10 步已依据用户报告记录 PASS，包括真实 MP4、补传合并及 MD5 一致性；数值、路径和录屏参数未提供，不能补造。详细证据边界见 ACCEPTANCE_RESULTS.md。未来扩展验收时记录分支 Commit、程序版本、显示器/DPI、截图工具版本、MP4 分辨率/FPS/时长、缺包数量、原始/恢复 MD5、日志及最终状态。真实双机 SMB、长视频、大文件完整传输、长时间播放、实际丢包率/精确 50 ms 节奏仍未验收；不能把 20fps 合成 AVI 或本次功能 PASS 作为这些项目的性能/硬件结果。
