# QRFT2100 独立命令行编码器：Windows 使用与测试手册

> **下载 ZIP 的用户直接从第 8 节开始，无需 Python 或 uv。** 第 0～7 节保留为源码/开发者操作。开发分支：`feature/encoder-cli-2100`，不需要 GUI、Control、Worker 或解码器。验收索引：[UA-012](USER_ACTIONS.md)。编码采用 **QRFT2100：2100 字节/包、v2 风格的三段大写 HEX、QR Version40-L**；与旧 v2 固定 1400 字节的解码器**不兼容**。协议见 [ENCODER_2100_PROTOCOL.md](ENCODER_2100_PROTOCOL.md)。

## 0. 最简单的使用方法：只填文件或文件夹路径

在已同步到本分支、安装了编码器依赖的 PowerShell 中执行：

```powershell
Set-Location 'D:\code_2026\qrft'
uv run --no-sync python -m qrft.encoder2100.cli play "D:\Videos\example.mp4"
# 文件夹自动在 RAM 打包；不需要 --zip 或 --folder
uv run --no-sync python -m qrft.encoder2100.cli play "D:\ExampleFolder"
```

**这条命令只有源路径是必须的，可以是文件或目录。** 这里的 MP4 是作为**普通二进制文件进行二维码编码**，不是对 MP4 进行解码；目录自动打包为内存 ZIP，详见第 7 节。启动后 CLI 静默等待，请手动输入 `qsnfj` 回车（输入不回显）；随后出现固定窗口，首张 START 静止等待。点击播放器窗口按 Space 开始/暂停/恢复，播放完保存录屏后按 Esc 退出。

默认参数：QRFT2100（2100 字节/包、全大写 HEX、v2 风格帧）、**50ms**、全部 DATA（0 到最后）、窗口模式、预缓存 4、根据 CPU 自动启动**最多 3 个二维码生成工作进程**。PowerShell **只用一行英文进度每约 5 秒原地刷新**，默认不生成本地播放日志，不需要 `--log`。例如：`[23:16:05] DATA 2645/30605 (8.6%) | elapsed 00:03:12`。完成显示 `DONE`，提前退出显示 `STOPPED`；暂停、二维码生成缓冲期间没有额外的中文提示。二维码生成时间可能超过 50ms，因此实际播放间隔可能更长；不会跳过数据包。

## 1. 全部命令与参数

```text
# 文件检查：只有源文件必填
uv run --no-sync python -m qrft.encoder2100.cli info "源文件"

# PNG 导出：源文件和全新的输出目录必填（不打开播放器）
uv run --no-sync python -m qrft.encoder2100.cli export "源文件" --output "新PNG目录"

# 二维码播放：只有源文件必填（默认无播放日志文件）
uv run --no-sync python -m qrft.encoder2100.cli play "源文件"
```

| 参数 | 用在哪个命令 | 是否必填 | 默认与说明 |
|---|---|---|---|
| 源路径 | `info / export / play` | **是** | 支持普通文件或文件夹，中文或空格请加引号；目录自动 RAM ZIP |
| `--max-archive-mib` | `info / export / play` | 否 | 默认 128，允许 4～4096；目录 RAM 预算含清单与余量，太小会安全拒绝；无磁盘回退 |
| `--expected-archive-md5` | `info / export / play` | 目录补传必填 | 原任务实际 ZIP MD5；目录选范围/缺包必须提供，错误则拒绝；普通文件不使用此参数 |
| `--output` | `export` | **是** | 新 PNG 目录，必须不存在，以免覆盖 |
| `--start-id` | `export / play` | 否 | 默认 0，按 DATA 包编号选择 |
| `--end-id` | `export / play` | 否 | 默认最后一包，闭区间（包含该编号） |
| `--missing` | `export / play` | 否 | 指定缺包 TXT，可与编号范围取交集 |
| `--interval-ms` | `play` | 否 | 默认 50，允许 1～60000，实际间隔可能延长 |
| `--prefetch` | `play` | 否 | 默认 4，允许 1～16 |
| `--workers` | `play` | 否 | 默认按 CPU 自动选择 1～3 个生成工作进程，显式设置可选 1～8 |
| `--fullscreen` | `play` | 否 | 默认固定非全屏，带上参数后全屏 |
| `--log` | `play` | 否 | **默认不创建日志**；只有主动指定全新 JSONL 文件才落盘供诊断 |

本命令行入口按照已确定的本地口令机制，在**解析参数前**静默校验 `qsnfj`，最多 3 次；不提供 `-h` / `--help`。未指定 `--workers` 时，自动按 `min(3, CPU数量)` 选择进程，CPU 数不可用时使用 1 个。工作进程数**不包含主进程**。

### 可选的自定义命令

```powershell
# 自定义速度（100ms）和生成进程数（3）
uv run --no-sync python -m qrft.encoder2100.cli play "D:\资料\test.zip" --interval-ms 100 --workers 3

# 指定 DATA 包 10～50（发送前也有 START/FINISH）
uv run --no-sync python -m qrft.encoder2100.cli play "D:\资料\test.zip" --start-id 10 --end-id 50

# 从缺包清单发送
uv run --no-sync python -m qrft.encoder2100.cli play "D:\资料\test.zip" --missing "D:\资料\missing.txt"

# 在需要排障时，才显式创建播放 JSONL 日志（必须使用不存在的新文件）
uv run --no-sync python -m qrft.encoder2100.cli play "D:\资料\test.zip" --log "D:\资料\play-debug.jsonl"
```

`--interval-ms`、`--workers`、`--prefetch` 不指定时都自动使用默认值。不要继续使用旧版 `--protocol v2`、`--chunk-size` 或 `--player` 参数：QRFT2100 独立编码器的 2100 字节分块与大写 HEX 是固定格式。

## 2. 首次准备（仅执行一次）

需要 Windows PowerShell、Git、uv；如果没有 uv，先安装并重开 PowerShell：`winget install --id astral-sh.uv -e`。

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
git status --short
# 如果上一条出现用户自己的未提交修改，请先保护修改，暂不切分支。
git fetch origin
git switch feature/encoder-cli-2100
git pull --ff-only origin feature/encoder-cli-2100
uv python install 3.12
uv sync --locked --python 3.12 --no-dev --extra encoder
```

本节仅准备环境；以后直接执行第 0 节的 `play "文件路径"` 即可。不要每次都重装依赖。命令必须在仓库目录且当前分支为 `feature/encoder-cli-2100`。

## 3. 基础测试：4201 字节文件的完整流程

在同一个 PowerShell 中一次建立独立测试目录和 4201 字节随机文件：

```powershell
Set-Location 'D:\code_2026\qrft'
$work = Join-Path $PWD ('temp\encoder2100-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$source = Join-Path $work '中文,MiX.bin'
$sample = [byte[]]::new(4201)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($sample) } finally { $rng.Dispose() }
[System.IO.File]::WriteAllBytes($source, $sample)
```

第一项：检查原始文件及预计 3 个 DATA（2100 + 2100 + 1）。

```powershell
uv run --no-sync python -m qrft.encoder2100.cli info "$source"
```

第二项：导出 PNG，不启动播放器，也不需要日志参数。

```powershell
$png = Join-Path $work 'qr-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --output "$png"
if ($LASTEXITCODE -ne 0) { throw 'PNG 导出失败' }
$manifest = Get-Content -LiteralPath (Join-Path $png 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$files = @(Get-ChildItem -LiteralPath $png -Filter '*.png' -File)
if ($manifest.complete -ne $true -or $manifest.packets -ne 3 -or $files.Count -ne 5) {
    throw 'PNG 数量、分块或完成状态异常'
}
if ($manifest.md5 -ne (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash) {
    throw 'MD5 不一致'
}
'PASS：3 DATA + 2 控制帧，共 5 张 PNG；源文件 MD5 正确'
```

第三项：最短的默认播放命令，没有 `--log`、速度或其他附加参数：

```powershell
uv run --no-sync python -m qrft.encoder2100.cli play "$source"
```

预期：先手动输入口令，首张 START 等待 Space；完成共 **5 帧**（START 1 + DATA 3 + FINISH 1），终端每约 5 秒刷新一行 DATA 数字进度，完成显示 DONE（无需中文缓冲提示）；FINISH 保留显示，按 Esc 后退出码 0。中途按 Esc 返回 130，**不代表已有屏幕录像文件丢失**。

第四项：缺包范围（补传）

```powershell
$missing = Join-Path $work 'missing.txt'
@('00000001', '00000002') | Set-Content -LiteralPath $missing -Encoding utf8
$retry = Join-Path $work 'retry-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --missing "$missing" --output "$retry"
if ($LASTEXITCODE -ne 0) { throw '缺包范围导出失败' }
$report = Get-Content -LiteralPath (Join-Path $retry 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.selected_packets -ne 2 -or $report.png_count -ne 4) { throw '补传结果不符合预期' }
'PASS：只导出 DATA 1 和 2，以及 START/FINISH'
```

所有导出目录都必须是**新目录**；文件存在时程序会拒绝覆盖，重试请换新目录。每次 CLI 启动都需要重新手动输入口令（输入不显示）。

## 4. 播放与录屏说明

- 播放器默认固定窗口，QR 白色区域大小 925×925，位置不随二维码帧变化；状态文字在区域外。
- 首帧静止等待 Space；Space 开始/暂停/恢复，Esc 退出；播放完成后最后一帧保留，先保存录屏再 Esc。
- START/FINISH 各一次，DATA 每包一次，总帧数为 N+2；空文件也有 START 和 FINISH，目录的空 ZIP 仍有自身字节和 DATA。
- 如果用 Windows 11 截图工具，框选**完整白色区域，包括静区**，不要裁掉边缘。默认 50ms 只是目标，二维码生成/调度可能使间隔延长。
- PowerShell 只显示英文数字进度：`[HH:MM:SS] DATA 已播放/总包数 (百分比) | elapsed HH:MM:SS`。启动后按 Space 才开始计时，每约 5 秒在**同一行**刷新；完成、提前退出、出错分别以 `DONE`、`STOPPED`、`ERROR` 结束并换行。暂停时包数不变，缓冲时没有额外提示。
- 默认**不生成本地播放日志**；只有指定 `--log` 才创建供排障使用的 JSONL（可保存详细缓冲事件）。
- MP4/ZIP/PDF/EXE 都可以作为**源文件二进制内容**编码；这里的 `play` 是播放二维码，不是直接播放 MP4 视频。
- 本阶段没有 QRFT2100 正式解码器，不能用旧 1400 字节协议的解码器验证新二维码。已做过独立 ZXing PNG/合成 MP4 检查，但真实 Windows 截图工具录屏的识别率仍未验收。

## 5. 常见报错

| 提示/现象 | 如何处理 |
|---|---|
| 程序启动无任何文字 | 正常：静默等待交互式口令 `qsnfj`，按 Enter；字符不回显 |
| 参数无效 | `play` 现在只需要文件名。其他动作按第 1 节参数表；未知旧参数仍会拒绝 |
| 找不到源文件 | 检查文件完整路径、引号及文件实际存在性 |
| 不能覆盖 PNG 目录 | `export --output` 必须选择尚不存在的新目录 |
| 无法创建自定义日志 | 只有显式 `--log` 才写文件，指定不存在的新路径 |
| workers 超出范围 | `--workers` 必须为 1～8；不指定时自动选 1～3 |
| 实际播放慢于 50ms | 不打印缓冲提示，窗口会保持上一帧直到下一张二维码准备完毕；可调大 `--prefetch` 或 `--interval-ms`，不跳包 |
| 屏幕空间不足 | 必须完整显示二维码与静区，不能裁切或模糊缩放 |
| 提前 Esc 返回 130 | 表示播放器没完整发送，不代表截图工具是否已经保存 MP4 |
| 码容量错误 | START 文件名太长可能溢出；不截断文件名或 2100 字节 DATA |

## 6. 开发者测试与历史证据

本轮文件夹内存 ZIP、稳定内容指纹、单次控制帧的最新验收和可复制命令见 [ENCODER_2100_FOLDER_TESTS.md](ENCODER_2100_FOLDER_TESTS.md)。以下 45 帧等数字属于此前控制帧各 20 次的历史证据，不适用于当前 N+2 序列。

编码器之前的 2100 字节 PNG/ZXing、45 帧合成 MP4、50ms 实际时序及历史 274 项回归结果见 [ENCODER_2100_ACCEPTANCE.md](ENCODER_2100_ACCEPTANCE.md) 与 [ENCODER_2100_METRICS.json](ENCODER_2100_METRICS.json)。**历史结果不能冒充这次 CLI 修改后的重新验证**。

要复测当前改动的关键用例（需先安装测试依赖）：

```powershell
Set-Location 'D:\code_2026\qrft'
uv sync --locked --python 3.12 --all-extras --group dev
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync pytest -q tests/test_encoder2100.py tests/test_encoder2100_folder.py
```

完整全量 pytest 和真实原生 Windows 播放器验收仍以当前提交对应的 CI 和 Windows 原生实测为准；CI 若没有触发或未通过，必须在验收记录中如实保留，不得借用旧提交结果。

**反馈方式：** 直接提供命令、屏幕中最后错误信息以及本次 PowerShell 输出；口令不要包含在终端记录中。

## 7. 文件夹内存 ZIP 与稳定内容 MD5

`info`、`play`、`export` 自动识别目录，无需额外模式开关。以下命令在交互式 PowerShell 中运行，手动输入口令；将示例目录换成实际目录：

```powershell
Set-Location 'D:\code_2026\qrft'
$folder = 'D:\ExampleFolder'
uv run --no-sync python -m qrft.encoder2100.cli info "$folder"
uv run --no-sync python -m qrft.encoder2100.cli play "$folder"
```

目录作为 `<folder>.zip` 传输：ZIP 全程保存在 RAM，原文件分块读取，不创建任何磁盘临时 ZIP。默认打包预算 128 MiB，可用 `--max-archive-mib` 显式设置 4～4096；超限直接报错，无磁盘回退。该预算包含 ZIP 和目录清单余量，不代表整个 Python/二维码进程树的内存上限。

`info` 同时显示文件数、子目录数、原始字节数、ZIP 大小、DATA 包数、内存估算及两种摘要：**Folder Content MD5** 标识稳定的相对路径/目录结构/文件内容；**Archive ZIP MD5** 校验实际发送字节，START 始终使用后者。修改时间或搬迁父目录不改变逻辑摘要；压缩库版本变化可能改变 ZIP 字节。因此目录选择性补传必须指定原任务 `--expected-archive-md5`，ZIP MD5 不同即拒绝，不能只凭 Folder MD5 混包。

所有输出目录及显式日志路径必须位于源目录之外。符号链接、Junction、循环目录及检测到的打包中增删改均拒绝；请保持源目录静止，当前检查不等同于 VSS 原子快照。

完整可复制的建样本、查看双摘要、时间戳不变性、PNG、缺包补传和内存限制操作见 [文件夹内存 ZIP 与稳定 MD5 测试说明](ENCODER_2100_FOLDER_TESTS.md)。本轮实际结果见 [验收记录](ENCODER_2100_ACCEPTANCE.md)；无需重复已完成的自动测试。

## 8. ZIP 解压后运行（发行用户推荐）

从 [encoder2100-v0.1.0 Release](https://github.com/yunfei00/qrft/releases/tag/encoder2100-v0.1.0) 下载 `QRFT-Encoder2100-Windows-x64-v0.1.0.zip` 与同名 `.zip.sha256`。先校验下载文件，再完整解压；**不要只复制 EXE，保留整个 QRFT-Encoder2100 目录与 _internal**。不安装 Python/uv、不进入源码目录。

```powershell
$downloads = Join-Path $HOME 'Downloads'
$zip = Join-Path $downloads 'QRFT-Encoder2100-Windows-x64-v0.1.0.zip'
$sum = Get-Content -LiteralPath ($zip + '.sha256') -Raw
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
if ($actual -ne ($sum.Trim() -split '\s+')[0]) { throw 'ZIP SHA256 不一致，请停止运行' }
$destination = Join-Path $downloads ('QRFT2100-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $zip -DestinationPath $destination
Set-Location (Join-Path $destination 'QRFT-Encoder2100')
.\QRFT-Encoder2100.exe info "D:\Data\example.bin"
.\QRFT-Encoder2100.exe play "D:\Data\ExampleFolder"
.\QRFT-Encoder2100.exe export "D:\Data\ExampleFolder" --output "D:\Output\QR"
```

最后三条请替换为实际存在的源路径及尚不存在的输出目录；每条启动后都静默等待手动输入 `qsnfj`、Enter，字符不可见，最多三次，不支持 -h/--help。首帧等待 Space；Space 开始/暂停/继续、Esc 退出，FINISH 保留到 Esc。完整白色区域录屏、50ms 目标、默认三进程和五秒英文进度行为同第 4 节，无默认日志。

所有第 1 节参数在 EXE 中保持相同，将源码命令前缀替换为 `.\QRFT-Encoder2100.exe` 即可。文件夹 RAM ZIP 默认预算 128 MiB，无磁盘中转；目录补传必须带原 Archive ZIP MD5：

```powershell
$originalArchiveMd5 = Read-Host '粘贴原任务 Archive ZIP MD5（32位HEX）'
.\QRFT-Encoder2100.exe play "D:\Data\ExampleFolder" --missing "D:\Data\missing.txt" --expected-archive-md5 $originalArchiveMd5
```

不要用 Folder Content MD5 替代 ZIP MD5。内存超限、源变化、错误 ZIP MD5、已有输出或输出位于源目录内均拒绝。冻结程序的三个生成子进程直接运行同一发行 EXE，不需要再次输入口令，也不调用系统 Python。

解压根目录包含 README.md、USER_GUIDE.md、VERSION.txt、SHA256SUMS.txt。VERSION 记录准确源 Commit、版本和构建库；内部校验表不包含自身。故障说明与版本验收边界见 [发行 README](ENCODER_2100_DISTRIBUTION_README.md) 和 [版本归档](ENCODER_2100_RELEASE.md)。真实 Windows 截图工具录屏/不同显示器识别率没有以合成视频冒充通过。
