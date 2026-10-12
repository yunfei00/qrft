# QRFT v2 中文操作与 Windows 11 真实录屏验收

日期：2026-10-12。本分支 0.4.0.dev0 是开发构建，未合并 main、未发布 Release。必须使用本分支构建或 Draft PR 的 CI 构件；旧 0.3.0rc1 EXE 不支持 v2。完整解压所有程序及运行库，不能只拷贝 EXE。协议见 PROTOCOL.md。

## Windows 11 真实录屏验收操作步骤（UA-009）

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

记录分支Commit、程序版本、系统/显示器/DPI、截图工具版本、MP4分辨率/FPS/时长、原始/恢复MD5、缺包数量、补传次数、日志与最终状态。先用小二进制/全字节文件验证，再做长文件。真实录屏、真实双机、实际丢包率和50ms实机节奏本轮尚未验收，用户提交这些证据后再评定，不能把20fps合成AVI视为真实MP4录屏。
