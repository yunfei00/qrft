# QRFT2100 P1 独立命令行编码器使用手册

当前新编码器唯一索引：[USER_ACTIONS.md 的 UA-012](USER_ACTIONS.md#ua-012qrft2100-p1-独立命令行编码器)。本阶段没有新 GUI、解码器或 EXE；旧协议、程序和文档保留。
格式详见 [ENCODER_2100_PROTOCOL.md](ENCODER_2100_PROTOCOL.md)，**不能把此协议交给旧 1400 字节解码器**。

## 1. Windows 11 源码安装

需要 Git、uv 和普通交互式 PowerShell。若未安装 uv，可在 PowerShell 执行 `winget install --id astral-sh.uv -e`，完成后重开终端。
以下命令在同一个 PowerShell 会话执行，目录已存在时使用该工作区，禁止覆盖未提交更改。

```powershell
$repo = 'D:\code_2026\qrft'
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    git clone https://github.com/yunfei00/qrft.git $repo
    if ($LASTEXITCODE -ne 0) { throw 'Clone 失败' }
}
Set-Location $repo
git status --short
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'fetch 失败' }
git switch feature/encoder-cli-2100
if ($LASTEXITCODE -ne 0) { throw '分支切换失败；请先保护工作区修改' }
git pull --ff-only origin feature/encoder-cli-2100
if ($LASTEXITCODE -ne 0) { throw '同步失败；不要强制覆盖' }
uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'Python 安装失败' }
uv sync --locked --python 3.12 --extra encoder
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
$work = Join-Path $repo ('temp\encoder2100-user-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$source = Join-Path $work '中文,MiX.bin'
[byte[]]$sample = New-Object byte[] 4201
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($sample) } finally { $rng.Dispose() }
[System.IO.File]::WriteAllBytes($source, $sample)
Write-Host "本轮文件及日志目录：$work"
```

预期：Python 3.12、依赖已同步，新文件为 4201 字节，预计 3 个 DATA（2100、2100、1）。安装不需要 Qt、Control 或 Worker。
若旧工作区有未提交更改，先保存；新检出分支不包含旧 v2 分支未合入 main 的内容。

## 2. 交互校验和文件检查

```powershell
uv run --no-sync python -m qrft.encoder2100.cli info "$source"
```

程序启动后静默等待，**手动输入小写 `qsnfj` 并按 Enter**；字符及星号不可见，没有提示文字是正常状态。
大小写敏感、最多三次，错误后非零退出。不支持 -h/--help，无交互终端、输入管道和重定向均拒绝；不可用环境变量或参数绕过。
这是本地操作限制，不是软件授权、防逆向或安全认证。不要把输入写入日志。
预期：显示原始文件名、大小、整体 MD5、预计 DATA 数；空文件为 0。
文件不存在、目录代替文件、START 文件名过长或编码期间源文件改变均报错，不能继续报告成功。

## 3. 导出 PNG（不打开窗口）

```powershell
$png = Join-Path $work 'png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --output "$png"
if ($LASTEXITCODE -ne 0) { throw 'PNG 导出失败；查看终端及 operations.jsonl' }
Get-Content -LiteralPath (Join-Path $png 'manifest.json') -Encoding UTF8
Get-FileHash -LiteralPath $source -Algorithm MD5
```

每条 CLI 命令都要再次手动校验。预期：`88888888.png`、`00000000.png`～`00000002.png`、`99999999.png`，共 5 张。
PNG 保存控制帧各一张，播放器重复各 20 次；manifest 明确保存重复次数。PNG 925×925、Version 40-L、强制字母数字模式。
文件 MD5 应与 manifest 一致；文件名原有大小写不改变。
输出目录必须不存在，已存在即拒绝，不覆盖用户文件。Ctrl+C 返回 130、保留部分 PNG 和 operations.jsonl；**没有 complete manifest 不算完成**。
重试请换新输出目录，不能把上次部分导出当成完整结果。权限错误、磁盘余量不足 1 MiB 时中止并报告。

## 4. 独立播放与固定区域录制

```powershell
$playLog = Join-Path $work 'playback.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --interval-ms 50 --prefetch 4 --log "$playLog"
```

预期：校验通过后打开固定窗口，首张 START 静止等待。点击窗口取得焦点，**Space 开始/暂停/继续，Esc 退出**，长按不会反复切换。
播放序列为 START 20 次、每个所选 DATA 一次、FINISH 20 次；播放完成保留最后二维码及 FINISHED 状态，先保存录像再 Esc。
提前 Esc/关闭窗口返回 130，正常播放完成后 Esc 返回 0；退出码与录像是否保存是不同事项。Ctrl+C 同样退出并关闭自有预生成进程。
控制文字、包号、剩余帧数位于二维码区域之外。默认客户端 945×1010，其中 (10,35) 起完整白色二维码区域为 925×925。
Version 40 的核心+静区 185 模块，每模块 5 像素，无模糊缩放。窗口不随帧改变；屏幕空间不足会报错，请使用更大工作区或显式全屏，不能裁切或缩放二维码。

可选全屏（使用新日志名）：

```powershell
$fullLog = Join-Path $work 'fullscreen.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --fullscreen --interval-ms 50 --log "$fullLog"
```

Windows 11 截图工具中选择“录制→新建”，框选**完整固定白色区域，包括四边静区**，开始录制后切回播放器按 Space。
完成后先停止录制保存 MP4，再 Esc；中途不改变窗口位置、DPI、录制框。实际硬件录屏识别率仍待验收，合成视频通过不能替代。
本阶段不提供正式解码器，不能使用旧解码器恢复 QRFT2100。自动识别证据见验收报告。

50 ms 是最短驻留目标，并非承诺稳定 20 FPS；调度、窗口刷新、二维码生成可能增加间隔。
使用两进程、有界预生成（1～16，默认 4）；缓存耗尽时显示 BUFFERING 并记录/输出等待信息，保持上一帧，**不丢弃后续包**。
日志中 `display.time` 为实际显示提交时刻，`state`/`buffering`/`completed`/`exit` 区分暂停、等待、完成和提前退出，不包含口令。

## 5. 编号范围和选择性补传

范围为原始 DATA 闭区间，起始默认 0，结束默认最后一包；超界拒绝。

```powershell
$rangeOutput = Join-Path $work 'range-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --start-id 1 --end-id 2 --output "$rangeOutput"
$missing = Join-Path $work 'missing.txt'
@('00000001', '00000002') | Set-Content -LiteralPath $missing -Encoding utf8
$retryOutput = Join-Path $work 'retry-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --missing "$missing" --output "$retryOutput"
$retryLog = Join-Path $work 'retry-playback.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --missing "$missing" --interval-ms 50 --log "$retryLog"
```

预期：只发送 DATA 1、2，保留原文件、2100 分块、编号及内容不变，START/FINISH 仍各 20 次；窗口和录屏区与普通传输完全相同。
清单支持单编号、`1-20` 闭区间、空行和 # 注释，自动合并去重、升序输出；越界或非法文本拒绝。最多 100000 个输入区间，避免无界编号列表。

## 6. 开发者自动验证与故障处理

不需要用户重跑 Codex 已完成的自动验收。需要复现时在源码目录执行：

```powershell
Set-Location $repo
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '测试依赖同步失败' }
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
$testTemp = Join-Path $work 'pytest'
uv run --no-sync pytest -q --basetemp "$testTemp"
$evidence = Join-Path $work 'benchmark'
uv run --no-sync python scripts/encoder2100_acceptance.py benchmark --root "$evidence"
```

benchmark 创建独立目录及约 1 GiB 流式测试文件，含 PNG/合成 MP4/JSON；先保证至少 3 GiB 空闲空间，不自动删除证据。
测试辅助脚本没有口令，直接调用编码核心做验收，不是普通用户 CLI，也不是正式解码入口。
详细结果与自动/物理边界见 [ENCODER_2100_ACCEPTANCE.md](ENCODER_2100_ACCEPTANCE.md)。
失败时保留终端报错、operations.jsonl、playback.jsonl、report.json；容量错误不截断名称、不降块，源文件改变则重新检查/导出到新目录。
