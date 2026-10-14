# QRFT2100 独立命令行编码器：Windows 使用与测试手册

> **现在应该从这里开始。** 本文针对分支 `feature/encoder-cli-2100` 的独立命令行编码器，使用 Python 3.12 + uv **运行源码**，不使用 EXE、不需要 GUI，也不需要 Decoder/Control/Worker。验收编号：[UA-012](USER_ACTIONS.md#ua-012qrft2100-p1-独立命令行编码器)。  
> 编码固定 **每包 2100 原始字节**、**全大写 HEX**、QR **Version 40-L / Alphanumeric**、925×925 像素，不能直接交给旧 1400 字节解码器。协议详见 [ENCODER_2100_PROTOCOL.md](ENCODER_2100_PROTOCOL.md)。

## 0. 先看这里：究竟怎么运行？

入口 `uv run --no-sync python -m qrft.encoder2100.cli` **不是完整的导出或播放命令**，它不带动作和文件路径，只会在口令通过后打印一行入口提示。真正使用时必须加上 **子命令、源文件和相应参数**。

最常用的三种写法（在本手册第 1 节配置好 `$source` 后直接复制）：

| 想做什么 | 复制这条 PowerShell 命令 | 执行结果 |
|---|---|---|
| 检查源文件 | `uv run --no-sync python -m qrft.encoder2100.cli info "$source"` | 文件名、原始字节数、MD5、DATA 包数 |
| 导出二维码 PNG | `uv run --no-sync python -m qrft.encoder2100.cli export "$source" --output "$png"` | 新目录中生成 PNG、`manifest.json`、`operations.jsonl` |
| 在窗口播放二维码 | `uv run --no-sync python -m qrft.encoder2100.cli play "$source" --interval-ms 50 --prefetch 4 --log "$playLog"` | 弹出固定二维码窗口，静止等 Space |

**重要：** 每运行一次 CLI，必须在 PowerShell 终端中**手动输入** `qsnfj` 并按 Enter，输入过程中不显示文字或星号；不是把口令写在命令后面。输入错误最多三次。程序有意不提供 `-h`/`--help`，参数完整说明见下面第 2 节。

只想用自己的文件？先完成第 1 节环境准备，再将 `$source` 改为自己的文件完整路径即可，其他命令可以原样使用。

## 1. 准备环境和一份可以验证的样本（只做一次）

在 **Windows PowerShell** 中复制**整个代码块**执行。后续第 3～6 节继续使用同一个 PowerShell 窗口，因为 `$source`、`$work` 等变量都定义在这里。

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'D:\code_2026\qrft'
$branch = 'feature/encoder-cli-2100'

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    if (Test-Path -LiteralPath $repo) { throw "目录存在但不是 Git 仓库：$repo；请换路径" }
    git clone --single-branch --branch $branch https://github.com/yunfei00/qrft.git $repo
    if ($LASTEXITCODE -ne 0) { throw 'Git 克隆失败' }
} else {
    if (git -C $repo status --porcelain) { throw '仓库有未提交修改，请先保留修改，不要覆盖' }
    git -C $repo fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'Git 获取失败' }
    if (git -C $repo branch --list $branch) {
        git -C $repo switch $branch
    } else {
        git -C $repo switch --track "origin/$branch"
    }
    if ($LASTEXITCODE -ne 0) { throw '分支切换失败' }
    git -C $repo pull --ff-only origin $branch
    if ($LASTEXITCODE -ne 0) { throw '同步失败，不能强制覆盖' }
}
Set-Location $repo
uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 安装失败' }
uv sync --locked --python 3.12 --no-dev --extra encoder
if ($LASTEXITCODE -ne 0) { throw '编码器依赖安装失败' }

$work = Join-Path $repo ('temp\encoder2100-manual-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$source = Join-Path $work '中文,MiX.bin'
$sample = [byte[]]::new(4201)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($sample) } finally { $rng.Dispose() }
[System.IO.File]::WriteAllBytes($source, $sample)

$png = Join-Path $work 'all-png'
$playLog = Join-Path $work 'normal-play.jsonl'
Write-Host "测试文件：$source"
Write-Host "本次工作目录：$work"
Get-Item -LiteralPath $source | Select-Object Name, Length
git branch --show-current
```

**预期：** 当前分支 `feature/encoder-cli-2100`，测试文件大小 **4201 字节**。按 2100 字节分块，正好 3 个 DATA 包（2100、2100、1）。所有输出只写入新建的 `temp/encoder2100-manual-随机ID`，不会覆盖旧任务。首次使用若没有 uv，可先执行 `winget install --id astral-sh.uv -e`，重开 PowerShell 再开始。

## 2. 完整命令结构和参数表

### 2.1 三种子命令

```text
uv run --no-sync python -m qrft.encoder2100.cli info   "源文件"
uv run --no-sync python -m qrft.encoder2100.cli export "源文件" --output "新PNG目录" [可选参数]
uv run --no-sync python -m qrft.encoder2100.cli play   "源文件" --log "新日志.jsonl" [可选参数]
```

其中 `"源文件"` 是已有**普通文件**的完整路径。即使文件名有中文、空格、逗号，也建议用双引号。

### 2.2 参数表（与当前 cli.py 源码一致）

| 参数或动作 | 用于 | 必填？ | 默认 / 有效值 | 示例 |
|---|---|---|---|---|
| `info` | 检查源文件 | 动作必选 | 无额外选项 | `info "$source"` |
| `export` | PNG 导出 | 动作必选 | 不打开窗口 | `export "$source" --output "$png"` |
| `play` | 窗口播放 | 动作必选 | 默认窗口、首帧等待 | `play "$source" --log "$playLog"` |
| `source`（源文件位置参数） | 三种动作 | **必填** | 已存在的文件路径 | `"D:\Files\资料.zip"` |
| `--output` | 仅 `export` | **必填** | **不存在**的新目录 | `--output "$png"` |
| `--log` | 仅 `play` | **必填** | **不存在**的新日志文件 | `--log "$playLog"` |
| `--start-id` | `export` / `play` | 可选 | 默认 0，从 0 开始的 DATA 编号 | `--start-id 1` |
| `--end-id` | `export` / `play` | 可选 | 默认最后一包；**包含结束编号** | `--end-id 2` |
| `--missing` | `export` / `play` | 可选 | 缺包清单 TXT 路径；与范围取交集 | `--missing "$missing"` |
| `--interval-ms` | 仅 `play` | 可选 | 默认 50；有效 **1～60000 毫秒** | `--interval-ms 100` |
| `--prefetch` | 仅 `play` | 可选 | 默认 4；有效 **1～16** | `--prefetch 8` |
| `--fullscreen` | 仅 `play` | 可选 | 不加为固定窗口；添加为全屏 | `--fullscreen` |

**不支持的选项：** 这版 CLI 没有 `--help`、`-h`、`--protocol`、`--chunk-size`、`--player`、`--workers` 等参数。QRFT2100 固定 2100 字节、Version 40-L，不要照搬旧版 v2 命令。

**范围和缺包规则：** `--start-id 1 --end-id 2` 表示发送 **DATA 1 和 2**，不是第 1～2 字节。若同时提供 `--missing`，实际发送的是缺包列表与该范围的交集。START 和 FINISH 总会分别发送（播放重复 20 次，PNG 导出各只保存一张）；范围越界会报错。0 字节文件没有 DATA，仍可以导出 START 和 FINISH。

## 3. 测试一：只检查文件，不导出（info）

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder2100.cli info "$source"
if ($LASTEXITCODE -ne 0) { throw 'info 失败，请查看终端错误信息' }
```

**操作：** 启动后窗口没有任何提示，手动输入 `qsnfj` 回车。此后输出 JSON，检查 `size` 为 **4201**、`packets` 为 **3**，并显示文件名和 32 位大写 MD5。测试文件是随机生成的，所以 MD5 **每次不同**；不要去对比文档里的某个固定哈希。

**通过条件：** 文件长度正确、包数 3、MD5 生成成功；整个过程没有打开二维码窗口。

## 4. 测试二：导出完整二维码 PNG（export）

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --output "$png"
if ($LASTEXITCODE -ne 0) { throw 'PNG 导出失败；请查看错误信息与日志' }

$manifestPath = Join-Path $png 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'manifest.json 不存在：导出未完成' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$pngFiles = @(Get-ChildItem -LiteralPath $png -Filter '*.png' -File)
$actualMd5 = (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash
if ($manifest.complete -ne $true) { throw '清单未标记完成' }
if ($manifest.packets -ne 3) { throw "包数不是 3：$($manifest.packets)" }
if ($manifest.png_count -ne 5 -or $pngFiles.Count -ne 5) { throw 'PNG 数量不等于 5' }
if ($manifest.md5 -ne $actualMd5) { throw '源文件 MD5 与导出清单不一致' }
Write-Host "PASS：5 张 PNG，3 个 DATA，MD5=$actualMd5"
Get-ChildItem -LiteralPath $png -Filter '*.png' | Select-Object Name, Length
```

**预期：** 输出目录中存在 `88888888.png`、`00000000.png`、`00000001.png`、`00000002.png`、`99999999.png` 共 **5 张**，以及 `manifest.json` 和 `operations.jsonl`。DATA 对应 2100、2100、1 字节；导出的是高密度 **925×925** PNG。控制帧只各保存 1 张，实际播放各重复 20 次。

**重要：** 导出目录必须事先不存在，命令会自行创建；同一 `$png` 不能再次用于导出。重试请改成一个全新的目录，例如 `$png = Join-Path $work 'all-png-retry'`。不覆盖现有 PNG 是正常保护行为。

## 5. 测试三：独立窗口播放（play）

```powershell
Set-Location $repo
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --interval-ms 50 --prefetch 4 --log "$playLog"
$playExit = $LASTEXITCODE
if ($playExit -eq 130) {
    Write-Warning '播放器提前结束：请检查是否未播放完就按 Esc 或关闭窗口'
} elseif ($playExit -ne 0) {
    throw "播放失败，退出码：$playExit；请检查日志：$playLog"
}
```

**手动操作：** 输入口令 → 等待首张 START 固定不动 → **点击播放器窗口获得焦点** → 按 Space 开始 → 中途 Space 暂停、再次 Space 恢复 → 等到 FINISHED → 如需录屏，**先保存录像** → Esc 关闭。

预期共 **43 次画面帧**：START 20 + DATA 3 + FINISH 20。首帧无限等待手动开始，不会倒计时；窗口固定且二维码在白色区域内不移动。实际 50ms 是最短驻留目标，生成和 Windows 调度可能使间隔更长，但不能静默跳包，出现 BUFFERING 会保持上一帧等待。

**默认布局：** 945×1010 客户区；白色二维码录屏区从客户区像素坐标 **(10,35)** 起，大小 **925×925**。状态文字在二维码之外。屏幕空间不足会明确报错，不能自动缩小二维码。

执行完检查日志（无需口令）：

```powershell
Get-Content -LiteralPath $playLog -Tail 12
```

其中 `event: "completed"` 表示播放到最后帧；`event: "exit"` 表示退出。**提前 Esc 可能退出码 130，不等于录屏文件不存在**。日志文件必须是新的文件名，不能覆盖旧日志。

### 5.1 实际录屏（可选，不属于自动测试）

Windows 11 截图工具 → 录像 → 新建 → 选择包含**完整静区的 925×925 白色区域** → 开始录制 → 再点击播放窗口按 Space → 完成后保存 MP4 → Esc。

当前项目**只有独立编码器**，还没有 QRFT2100 正式解码器；旧 1400 字节解码器不能用于此视频。现有 ZXing PNG/合成 MP4 验收通过，不代表真实 Windows 截图工具录屏已经通过。

### 5.2 改变播放速度、预缓存或全屏

```powershell
$slowLog = Join-Path $work 'slow-play.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --interval-ms 100 --prefetch 8 --log "$slowLog"
```

```powershell
$fullLog = Join-Path $work 'fullscreen-play.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --fullscreen --interval-ms 50 --log "$fullLog"
```

每条命令都要重新输入口令。窗口播放完成后再按 Esc 退出。指定 `--fullscreen` 前先确认当前显示器足够容纳完整二维码布局；不必为了验证基础功能而重复这些可选操作。

## 6. 测试四：指定范围和缺包补传（不需要正式解码器）

文件有 3 个 DATA，编号分别为 0、1、2。以下使用**新目录、新日志**，不影响此前导出。

### 6.1 只导出 DATA 1～2

```powershell
$rangePng = Join-Path $work 'range-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --start-id 1 --end-id 2 --output "$rangePng"
if ($LASTEXITCODE -ne 0) { throw '指定范围导出失败' }
Get-ChildItem -LiteralPath $rangePng -Filter '*.png' | Select-Object Name
```

**预期 4 张 PNG：** START、DATA 00000001、DATA 00000002、FINISH。

### 6.2 准备 missing.txt，只补传 DATA 1～2

```powershell
$missing = Join-Path $work 'missing.txt'
@('00000001', '00000002') | Set-Content -LiteralPath $missing -Encoding UTF8
$retryPng = Join-Path $work 'retry-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --missing "$missing" --output "$retryPng"
if ($LASTEXITCODE -ne 0) { throw '缺包导出失败' }
Get-Content -LiteralPath (Join-Path $retryPng 'manifest.json') -Raw -Encoding UTF8
```

**预期：** `selected_packets=2`、`png_count=4`；START/FINISH 不变，DATA 1、2 内容和原编号保持一致。

### 6.3 播放补传二维码（可选）

```powershell
$retryLog = Join-Path $work 'retry-play.jsonl'
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --missing "$missing" --interval-ms 50 --log "$retryLog"
```

完成共 42 帧（START 20 + DATA 2 + FINISH 20）。缺包文件支持单编号、闭区间如 `1-2`、空行及 `#` 注释，自动去重并排序。非法或超出总包数的编号会报错，不能发送。

## 7. 换成你自己的文件（实用模板）

完成第 1 节的环境同步后，把以下 **`$source` 改成你实际存在的文件**，可以是 ZIP、EXE、BIN、PDF 或任意其他文件；不需要先压缩、不限制文件扩展名。输出目录和日志使用新的时间标识，避免覆盖之前的结果。

```powershell
Set-Location 'D:\code_2026\qrft'
$source = 'D:\MyFiles\sample.zip'  # 必须换成你真实存在的文件
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "找不到文件：$source" }
$work = Join-Path $PWD ('temp\encoder2100-own-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$png = Join-Path $work 'png'
$playLog = Join-Path $work 'play.jsonl'

# ① 检查文件（先手动输入口令）
uv run --no-sync python -m qrft.encoder2100.cli info "$source"

# ② 需要保存图片时运行这条（重新输入口令）
uv run --no-sync python -m qrft.encoder2100.cli export "$source" --output "$png"

# ③ 需要播放/录屏时运行这条（重新输入口令）
uv run --no-sync python -m qrft.encoder2100.cli play "$source" --interval-ms 50 --log "$playLog"
```

上面三条是**三种可独立使用的操作**，不是每次都要全做。只看信息就运行 ①；只导出 PNG 就运行 ②；只播放就运行 ③。

大文件导出 PNG 可能产生大量图片、花费较长时间；有界内存并不等于磁盘空间无限。建议先通过 `info` 看包数，再决定是否导出全部或只播放指定范围。

## 8. 常见错误与判断标准

| 现象 | 原因 / 下一步 |
|---|---|
| CLI 运行后黑屏/无提示 | 正常的隐藏口令等待；手动输入 `qsnfj` 并回车，不会显示输入 |
| 三次校验失败 | 大小写敏感；重新执行命令，再手动输入，避免添加空格或换行 |
| 参数无效 | 查看第 2 节：`export` 缺少 `--output`、`play` 缺少 `--log`，或使用了旧版参数 |
| `--help` 无效 | 该 CLI 设计为不提供帮助开关，所有参数在第 2 节 |
| `output` 目录已存在 | 导出有防覆盖保护，改用新目录 |
| `play.jsonl` 已存在 | 日志使用 `open("x")`，改一个新日志文件名 |
| 屏幕空间不足 | 至少完整容纳 945×1010 客户区；不能通过裁剪或非整数缩小规避 |
| PNG/START 容量溢出 | QR 40-L 容量有上限；文件名过长可能溢出，程序不得截断源数据 |
| BUFFERING 或实际帧率不足 20fps | 二维码生成速度和调度造成等待；不会跳过包，查看日志时序 |
| 播放提前退出码 130 | 尚未 FINISHED 就 Esc/关闭；已有录像是否保存另行检查 |
| 磁盘/权限错误或中断 | 保留部分输出和 `operations.jsonl`；无 `complete=true` 的 manifest 不能标记导出成功 |

**基础验收只需按顺序完成第 1、3、4、5、6 节**；第 7 节是真实文件模板，第 9 节是开发者自动化测试，不需要普通用户重复跑。

## 9. 已完成的自动化验证（开发者可选复现）

Codex 已测试真正的 ZXing PNG 字节往返、100/100 个 2100 字节满载 PNG、45/45 个合成 MP4 帧、原生 Space/Esc 播放器以及边界/异常测试。历史数据与限制在 [ENCODER_2100_ACCEPTANCE.md](ENCODER_2100_ACCEPTANCE.md)、[ENCODER_2100_METRICS.json](ENCODER_2100_METRICS.json)。这些测试**不是**你使用 Windows 截图工具时的物理录屏验收。

仅开发者需要复现全量回归时，先确认至少 3 GiB 可用空间（基准脚本会生成约 1 GiB 临时文件、100 PNG 和合成 MP4），使用独占输出目录：

```powershell
Set-Location $repo
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '开发依赖同步失败' }
uv run --no-sync ruff format --check .
if ($LASTEXITCODE -ne 0) { throw 'Ruff 格式失败' }
uv run --no-sync ruff check .
if ($LASTEXITCODE -ne 0) { throw 'Ruff 静态检查失败' }
$testTemp = Join-Path $work 'pytest'
$oldBlas = $env:OPENBLAS_NUM_THREADS
$oldOmp = $env:OMP_NUM_THREADS
try {
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:OMP_NUM_THREADS = '1'
    uv run --no-sync pytest -q --basetemp "$testTemp"
    if ($LASTEXITCODE -ne 0) { throw 'pytest 失败' }
    $benchmark = Join-Path $work 'benchmark'
    uv run --no-sync python scripts/encoder2100_acceptance.py benchmark --root "$benchmark"
    if ($LASTEXITCODE -ne 0) { throw '独立编码验收失败' }
} finally {
    $env:OPENBLAS_NUM_THREADS = $oldBlas
    $env:OMP_NUM_THREADS = $oldOmp
}
```

当前历史验收记录为 274 passed，0 failed，0 skipped；实际重新运行结果以当次环境为准。测试脚本使用编码核心和独立 ZXing 校验器，**不是用户 CLI 口令绕过入口，也不是正式解码软件**。

---

**反馈方式：** 如果按某一步执行失败，只提供“第几节 + PowerShell 最后错误信息 + 本轮 `$work` 目录”。不要发送真实口令、隐私文件或不必要的完整录像。成功时可以反馈“QRFT2100 使用手册第 1、3、4、5、6 节通过”。
