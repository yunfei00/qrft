# QRFT v2-P9：Windows 11 源码视频解码手册

当前推荐 Python 3.12 + uv 源码运行。GUI 没有编码 CLI 的口令限制；不需要输入 qsnfj。不打包 EXE、不发布版本，PR #7 保持 Draft。编码、补传二维码仍按 [v2 编码手册](V2_USER_GUIDE.md)，已通过的 P8 验收不要求重做。

## 1. 准备源码与依赖

以下命令在 PowerShell 执行，已有仓库先确认没有自己的未提交修改；不要执行 reset 或强推。若 uv 未安装，先在终端执行官方安装命令，再重新打开 PowerShell：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

```powershell
$repo = 'D:\code_2026\qrft'
if (-not (Test-Path (Join-Path $repo '.git'))) {
    git clone https://github.com/yunfei00/qrft.git $repo
}
Set-Location $repo
git status --short
# 工作区有自己的修改时，先提交或另行备份，不要直接继续切换。
git fetch origin
git switch feature/qrft-v2-hex-md5
git pull --ff-only origin feature/qrft-v2-hex-md5
uv python install 3.12
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '依赖同步失败，请检查网络及 uv 输出' }
```

预期：Python 3.12、`.venv` 和全部已有可选依赖就绪；安装失败不得跳过识别依赖。

## 2. 单机一键启动

```powershell
$repo = 'D:\code_2026\qrft'
$workspace = 'D:\code_2026\qrft-decoder-tasks'
Set-Location $repo
uv run --no-sync python -m qrft.decoder_gui.main --workspace $workspace
```

预期：中文窗口默认单机模式，自动启动带随机 Token 的 localhost Control，无须另外启动服务、浏览器、Worker 或配置 Token。首次使用选择一个专用工作目录；已有任务目录在重开后自动加载，不能选择他人的 `.qrft-decoder` 数据目录。非敏感工作目录、采样 FPS、Worker 数量、时间片设置保存到 Windows 当前用户的 Qt 设置。Token 仅保留在内存及子进程环境，不保存到 Qt 设置。

“设置”允许切换工作目录后点击“打开工作区”；工作目录同时决定任务输出和日志位置。默认采样 60 FPS，避免遗漏 50 ms DATA；时间片默认 30 秒，边界重叠 1 秒。短片多进程验证可改为 1 秒时间片（重叠 0.1 秒）。不改变任何二维码线协议或编码参数。

## 3. 新建任务与导入 MP4

在“任务与恢复”点击“新建任务”，输入名字，选择 v2（旧录像选择 v1）。每个任务只对应一个原文件，协议建立后锁定。点击“添加视频 / 同任务补传”，选择一个或多个 MP4/AVI，或拖拽到窗口；确认这些录像确属同一原文件。视频列表显示路径、时长和时间片完成数。

v2 DATA 没有文件 ID，应用无法凭 DATA 自动证明来源。START 与当前任务不一致、混入 v1、MD5 或块长度错误会拒绝提交；合法但来自另一文件的 DATA 仍须依靠用户正确关联及最终文件 MD5 检验。MD5 是完整性校验，不是安全认证。

点击“开始 / 继续”。后台启动独立本机 Worker，GUI 保持响应。“节点与时间片”可查看唯一节点 ID、心跳、租约持有者、重试次数、检查点和错误；“实时日志”显示 Control/Worker 原始日志（界面隐藏 Token）。START 未识别时显示“等待 START”，不虚构总包数。扫描进度和有效包完整率是两条独立进度条。

预期：全片扫描后自动检查缺包并尝试恢复，只有满足现有协议的全部条件和文件哈希才显示“恢复成功”。扫描完成不代表恢复成功。v2 无 FINISH 也可在包完整、MD5 正确时成功；v1 保留 FINISH、CRC32、SHA256、MD5 校验规则。

## 4. 缺包、补传与恢复

有缺包时选择“导出缺包 TXT / CSV / JSON”，选择一个没有同名报告的新目录。TXT 中每行保留原始 8 位编号，可直接在既有编码 GUI 导入 `missing.txt`；不要改变原文件、分块、编号或内容。编码播放及 Windows 截图工具录制按 [V2_USER_GUIDE](V2_USER_GUIDE.md) 的固定白色区域与 Space / Esc 步骤执行。

回到原任务，点击“添加视频 / 同任务补传”导入新 MP4，再“开始 / 继续”。已扫描完成的时间片无需重做，SQLite 合并之前与补传视频的数据；相同包幂等计为重复，不覆盖；不同有效内容进入冲突隔离。晚到 START 可绑定此前持久化 DATA。

预期：缺包为 0、没有阻止恢复的冲突，最终哈希一致才恢复成功。“打开结果目录”打开本机结果；在分布式模式结果位于控制机，远端路径不一定能在当前电脑直接打开。任务自动保存，无须手动移动包或编辑 SQLite。

本机文件位置：

- 数据库：`工作目录\.qrft-decoder\control.sqlite3`。
- 原始节点日志：`工作目录\.qrft-decoder\logs\`（每次启动新日志）。
- 缺包报告：`工作目录\.qrft-decoder\outputs\任务ID\missing.*`；另可在 GUI 导出到新目录。
- 恢复文件：`工作目录\.qrft-decoder\outputs\任务ID\files\原文件名`。
- 恢复证据：SQLite 中保留 MD5、SHA256、路径、状态，GUI 成功提示及日志可查看。

手动核对哈希（用文件对话框选择实际路径，不依赖示例文件名）：

```powershell
Add-Type -AssemblyName System.Windows.Forms
$pick = New-Object System.Windows.Forms.OpenFileDialog
$pick.Title = '选择原始文件'
if ($pick.ShowDialog() -ne 'OK') { throw '未选择原始文件' }
$original = $pick.FileName
$pick.Title = '选择恢复文件'
if ($pick.ShowDialog() -ne 'OK') { throw '未选择恢复文件' }
$restored = $pick.FileName
$originalMd5 = (Get-FileHash -LiteralPath $original -Algorithm MD5).Hash
$restoredMd5 = (Get-FileHash -LiteralPath $restored -Algorithm MD5).Hash
if ($originalMd5 -ne $restoredMd5) { throw 'MD5 不一致，验收失败' }
'MD5 一致：' + $restoredMd5
```

已有结果文件不会覆盖；验证成功后无需再次点击恢复。文件名非法、磁盘空间不足、写入权限不足、MD5 错误或冲突不能计为成功。

## 5. 暂停、继续、停止、取消与重开

暂停和“停止并保存”都停止 GUI 启动的本机 Worker，撤销当前任务的有效租约，保留包、检查点和已完成时间片；“开始 / 继续”重新启动扫描。最多有一个尚未提交的批次需重新识别，不会丢失已确认包；从已持久化检查点前 1 秒重扫，重复提交幂等。

“取消任务”禁止继续领取和提交，保留数据；明确点击“开始 / 继续”可解除取消。暂停也作用于当前任务的远程 Worker，旧租约的提交会被拒绝。远程 Worker 可继续处理其他任务。

关闭窗口停止本程序创建的本机 Worker 和本地 Control，保存任务，不删除视频、数据库、日志或结果；忙碌时界面显示关闭进度，等待后台完成与清理。远程 Control 和用户自行启动的 Worker 不会被关闭。重开同一工作目录后选择已有任务继续。异常退出后租约超时允许重新分配，已收到包保留。

“重新扫描视频”只重新排队当前任务的视频时间片，已有包保留；之后点击开始。不要用重新扫描处理来源错误或内容冲突，请建立新的隔离任务。

## 6. 本机两个独立 Worker 的自动验证

自动化已有真实 MP4、HTTP、两个独立进程、漏包/补传/哈希测试，不需要用户重复跑才能完成本阶段。维护时可复制：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
$testTemp = Join-Path $repo ('temp\p9-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testTemp | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = $testTemp
uv run --no-sync pytest -q tests/test_decoder_desktop.py tests/test_v2_integration.py
```

GUI 中设置本机 Worker 数 2、短录像时间片 1 秒，也可查看两个节点实际领取不同时间片。两个本机进程不是两台电脑，不代表真实 SMB 已验收。

可重复性能测量：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
uv run --no-sync python scripts/decoder_benchmark.py --size-kib 64 --workers 2
```

脚本每次创建独占 `temp\decoder-benchmark-随机ID`，生成真实合成 MP4，统计整个 Control/Worker 进程树 CPU、RSS、I/O、有效包率与恢复时间，保存 `report.json`，不删除用户资源。不把哈希速度、合成视频扫描速度当成真实录屏传输速度；大规模测试会很耗时，当前 64 KiB 测量不证明 1 GB 或长视频性能。

## 7. 分布式控制中心与其他 Windows 节点

控制机在专用终端启动源码 Control；Token 使用隐藏输入，不能写在 URL、命令行参数、日志或公开 JSON。以下专用目录需只用于 QRFT。LAN 需按实际网络开放端口，仅允许可信节点；跨不可信网络须 HTTPS 反向代理，不传输明文 Token。

```powershell
$repo = 'D:\code_2026\qrft'
$controlRoot = 'D:\code_2026\qrft-control-p9'
Set-Location $repo
New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
$secret = Read-Host '输入控制中心 API Token（隐藏）' -AsSecureString
$env:QRFT_API_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
$env:QRFT_DB_PATH = Join-Path $controlRoot 'control.sqlite3'
$env:QRFT_OUTPUT_DIR = Join-Path $controlRoot 'outputs'
uv run --no-sync python -m qrft.control.app --host 0.0.0.0 --port 8787
```

另一个终端打开第 2 节 GUI，切换“分布式模式”，输入控制机 HTTP 地址和同一 Token，再连接。服务器 GUI 也可以用 `http://127.0.0.1:8787` 连接。添加视频前选择所有节点都能读取的只读 UNC 路径，例如 `\\控制机\QRFTVideos\capture.mp4`，不要登记只在控制机存在的 D: 路径。GUI 导入时也需要能读该共享；SMB 凭据通过 Windows 正常共享登录配置，不保存到 QRFT。创建任务、选择原文件、导入共享录像、开始时本机 Worker 自动加入；网页管理 API 保留兼容。

其他 Windows 电脑先执行第 1 节环境准备，在 PowerShell：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
$server = Read-Host '输入控制中心地址，例如 http://192.168.1.10:8787'
$node = $env:COMPUTERNAME + '-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$secret = Read-Host '输入同一个 API Token（隐藏）' -AsSecureString
$env:QRFT_API_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
uv run --no-sync python -m qrft.decoder.worker --server $server --node-id $node --sample-fps 60
```

预期：节点自动心跳、领取时间片、读取 SMB、校验并提交；无需 GUI 编码口令。Ctrl+C 退出；未完成租约到期重领，已提交包保留。服务器 GUI 可查看节点状态、错误和重领次数；默认远端 Worker 可领取所有可用任务，必要时追加 `--task-id 数字任务ID` 限定任务。环境变量 Token 只用于当前终端，可在退出后执行 `Remove-Item Env:QRFT_API_TOKEN`。

真实双机验收：在 B 上确认共享可读；登记较长真实 MP4，A/B 都完成时间片；处理中断开 B 的网络或退出 Worker，等待租约到期并由 A 重领；重新接入 B；补传后最终 MD5 一致。保留两端日志、任务/节点 ID、时间片 attempts、哈希和系统信息。当前真实双 Windows/SMB 未验收，不能用本机测试代替。

## 8. 开发者原生自动验收与性能基准

验收运行器会启动真实 PySide6 GUI、Control 和独立 Worker 进程，生成专用 MP4/测试数据并操作本机 GUI。只在可交互的 Windows 桌面运行；不要将工作区指向已有用户任务目录。每次必须使用新的临时目录：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
$stamp = [guid]::NewGuid().ToString('N')
$base = Join-Path $repo ("temp\p9-native-acceptance-" + $stamp)
New-Item -ItemType Directory -Path $base | Out-Null
$reportDir = Join-Path $base 'run'
$workspace = Join-Path $base 'workspace'
uv run --no-sync python -m qrft.decoder_gui.main --acceptance-output $reportDir --workspace $workspace --acceptance-stability-seconds 60
```

预期：进程退出码 0，`run\report.json` 为 27 PASS、0 FAIL，物理双机/SMB 一项列为 NOT TESTED；HTML 报告、截图、GUI 日志、测试数据库和 Control/Worker 日志留在 `run` 及 `workspace`。失败会生成带失败位置的 JSON 并返回非零。不要把本机多 Worker 结果当作第二台物理电脑验收。长 GUI 稳定性可将 60 调为 600、1800 或 3600 秒；过程可用 Ctrl+C 取消，取消时会尝试关闭本次创建的进程。

可独立运行重复性能测量，输出只代表合成 MP4：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
$stamp = [guid]::NewGuid().ToString('N')
$benchmarkDir = Join-Path $repo ("temp\p9-benchmark-" + $stamp)
uv run --no-sync python scripts/decoder_benchmark.py --size-kib 64 --workers 2 --directory $benchmarkDir
```

预期：`report.json` 记录编码/扫描/恢复、有效包速率、CPU/RSS/I/O 和哈希；合成二维码吞吐不代表屏幕录制速度。更大数据会明显增加实际生成二维码和扫描时间；不能把哈希性能当二维码速度。

## 9. 错误处理与最终人工验收

无法打开视频：核对本机/UNC 路径、SMB 权限、MP4 编码和是否已完整保存。没有 START：补录包含 START 的同一文件录像，不能编造缺包。缺包：导出 TXT，录制选择性补传，导入原任务。协议/文件混用或有效内容冲突：建立新的隔离任务。网络中断：Worker 重试，失效租约重新分配；不能将错误时间片标为完成。文件已存在：应用拒绝覆盖，选择新任务目录或查看既有已验证结果。空间不足/权限问题：修复环境后保留原任务重试恢复。详细日志位于工作目录 `.qrft-decoder\logs`，对外提供前检查私人路径与数据，不提供 Token。

本地原生 GUI 自动验收已按 [UA-011](USER_ACTIONS.md) 完成，详细结果、性能指标及未验收边界见 [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md)。完整 HTML/JSON 报告、GUI 截图和 Control/Worker 日志保存在该记录列出的独占 `temp/p9-native-acceptance-*` 目录。自动生成的真实可解码 MP4 不是 Windows 截图工具录屏；P8 用户报告的录屏验收仍单独保留。真实双 Windows/SMB、物理断网及重连仍待第二台电脑，按本手册第 7 节执行，本机多进程不替代现场验收。
