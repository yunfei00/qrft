# QRFT2100：文件夹内存 ZIP、稳定 MD5 与单次控制帧

本轮源码功能已自动验证，不需要用户重复这些测试。用户操作索引仍为 [UA-012](USER_ACTIONS.md)，日常入口见 [编码器手册](ENCODER_2100_USER_GUIDE.md)。分支 `feature/encoder-cli-2100`，不开发解码器、GUI 或 EXE。

## 1. 两种 MD5 必须分开

- **Folder Content MD5 / SHA256**：按 [协议](ENCODER_2100_PROTOCOL.md#文件夹传输与两种摘要) 的类型、路径长度、相对路径、内容长度、内容序列计算。根名称、绝对父路径、时间、权限、ZIP 元数据不参与。文件路径、大小写、字节及空目录变化会改变摘要。
- **Archive ZIP MD5 / SHA256**：对实际 BytesIO ZIP 全部字节计算。**START 的 MD5 始终是 Archive ZIP MD5**，DATA 分块的也是 ZIP 字节，不能替换成逻辑摘要。

ZIP comment 保存规范版本 `QRFT2100-FOLDER-1` 和稳定逻辑摘要，不生成用户目录内的清单文件。固定排序、时间 1980-01-01、权限/平台、DEFLATED level=6 等规则见协议。
同环境测试生成的 ZIP 完整字节、MD5、SHA256 一致；Python/zipfile/zlib 版本变化仍可能改变 ZIP 字节。`info` 和 export manifest 记录 Python、zlib 编译/运行版本。
**即使 Folder MD5 相同，只要 ZIP MD5 不同，就不能混合 DATA**。目录缺包/范围补传必须提供原任务 `--expected-archive-md5`，重新打包并比对后才允许发送；底层 Source 的部分范围同样受此保护。
MD5 是完整性检查和本地任务标识，不是防恶意篡改认证。

## 2. 从零建立源码环境与目录样本

在已安装 Git/uv 的 PowerShell 中执行。当前仓库已检出时不要重复 clone，也不要覆盖未提交修改；首次获取可先执行 `git clone https://github.com/yunfei00/qrft.git D:\code_2026\qrft`。

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
git status --short
git fetch origin
git switch feature/encoder-cli-2100
if ($LASTEXITCODE -ne 0) { throw '分支切换失败，请先保护本地修改' }
git pull --ff-only origin feature/encoder-cli-2100
if ($LASTEXITCODE -ne 0) { throw '同步失败' }
uv python install 3.12
uv sync --locked --python 3.12 --no-dev --extra encoder
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
$work = Join-Path $repo ('temp\folder2100-user-' + [guid]::NewGuid().ToString('N'))
$folder = Join-Path $work '示例 MiX'
New-Item -ItemType Directory -Path $folder | Out-Null
New-Item -ItemType Directory -Path (Join-Path $folder '空目录') | Out-Null
New-Item -ItemType Directory -Path (Join-Path $folder 'Nested Space') | Out-Null
[System.IO.File]::WriteAllBytes((Join-Path $folder 'Zero.bin'), [byte[]]::new(0))
[System.IO.File]::WriteAllBytes((Join-Path $folder '.hidden'), [byte[]](0,255,1,128))
$binary = [byte[]]::new(5003)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($binary) } finally { $rng.Dispose() }
[System.IO.File]::WriteAllBytes((Join-Path $folder 'Nested Space\中文,#&[].EXE'), $binary)
Write-Host "本次目录：$work"
```

预期：仅创建本轮独立样本，原有文件不变；没有 ZIP 文件。隐藏文件无排除规则（Windows 隐藏属性和点文件均读取），所有普通文件和空/非空目录都纳入。目录计数不包含根本身，但根在逻辑摘要中有空路径 D 标记。

## 3. info、默认播放与 PNG

每次 CLI 启动后手动输入 `qsnfj` 并回车，字符不可见；大小写敏感、最多三次。仍不支持 -h/--help 或输入管道绕过。

```powershell
$firstJson = uv run --no-sync python -m qrft.encoder2100.cli info "$folder"
if ($LASTEXITCODE -ne 0) { throw '目录打包失败' }
$first = ($firstJson -join [Environment]::NewLine) | ConvertFrom-Json
$first | Format-List name,file_count,directory_count,folder_content_md5,folder_content_sha256,archive_zip_md5,archive_zip_sha256,zip_size,packets,archive_buffer_allocated_bytes,memory_budget_bytes,memory_limit_bytes,python_version,zlib_runtime_version
uv run --no-sync python -m qrft.encoder2100.cli play "$folder"
$png = Join-Path $work 'png'
uv run --no-sync python -m qrft.encoder2100.cli export "$folder" --output "$png"
if ($LASTEXITCODE -ne 0) { throw 'PNG 导出失败' }
```

info 的输出捕获只重定向 stdout，stdin/stderr 必须仍连接交互终端，口令手动输入。没有通过 stdin 喂口令。
预期：名称 `<folder>.zip`，size/zip_size 为实际 ZIP 字节，packets=`ceil(zip_size/2100)`。info 的 md5 与 archive_zip_md5 相同，通常与 folder_content_md5 不同。
play 自动判断目录，不需要 --folder/--zip；显示两种 MD5、ZIP 大小与包数后打开固定窗口。**START 一次→DATA N 次→FINISH 一次，总计 N+2**；首帧等待 Space，完成后 FINISH 保留到 Esc，逻辑控制帧不循环 20 次。屏幕录制可能自然捕获同一驻留码的多个视频帧，这不等于序列重复发送。
默认间隔仍 50ms、最多 3 个生成工作进程、每约 5 秒原地刷新一行英文进度，无默认播放日志；需要诊断才显式提供 --log 新路径。PNG 仍有 START/FINISH 各一张，manifest.control_repeats=1。

## 4. 验证时间、路径不影响摘要与 ZIP；安全补传

保持同一个 PowerShell 会话：

```powershell
Get-ChildItem -LiteralPath $folder -File -Recurse -Force | ForEach-Object {
    $_.LastWriteTimeUtc = [DateTime]::Parse('2020-01-01T00:00:00Z').ToUniversalTime()
}
$secondJson = uv run --no-sync python -m qrft.encoder2100.cli info "$folder"
if ($LASTEXITCODE -ne 0) { throw '第二次打包失败' }
$second = ($secondJson -join [Environment]::NewLine) | ConvertFrom-Json
if ($first.folder_content_md5 -ne $second.folder_content_md5 -or $first.archive_zip_md5 -ne $second.archive_zip_md5 -or $first.archive_zip_sha256 -ne $second.archive_zip_sha256) {
    throw '仅更改时间戳时摘要不应改变'
}
$missing = Join-Path $work 'missing.txt'
'00000000' | Set-Content -LiteralPath $missing -Encoding utf8
$retryPng = Join-Path $work 'retry-png'
uv run --no-sync python -m qrft.encoder2100.cli export "$folder" --missing "$missing" --expected-archive-md5 $first.archive_zip_md5 --output "$retryPng"
if ($LASTEXITCODE -ne 0) { throw 'ZIP 补传一致性检查失败' }
uv run --no-sync python -m qrft.encoder2100.cli play "$folder" --missing "$missing" --expected-archive-md5 $first.archive_zip_md5
```

预期：两次逻辑摘要/ZIP 摘要一致，补传只含 DATA 0 加两个控制帧，对应 DATA 内容与原任务完全相同。不提供 expected-archive-md5、使用错误值或逻辑摘要代替 ZIP 摘要均拒绝目录补传。普通文件不使用此选项，旧文件范围/缺包用法保留。
更改目录内文件后，应视为新的传输，不自动沿用旧编号内容。跨环境 ZIP 不一致时，即使逻辑摘要一致，也必须拒绝混包；用原环境、原目录和原 ZIP MD5 重新检查，不能强制覆盖校验。

## 5. RAM、源一致性与失败处理

目录构造只用 `io.BytesIO` + `zipfile.ZipFile`，每次原文件读取最多 64 KiB，ZIP 完成后以只读 seek/read 视图按 2100 分块。没有 tempfile/SpooledTemporaryFile、磁盘 ZIP、缓存 ZIP 或写后删 ZIP；PNG、显式诊断日志和测试 MP4 是用户请求的输出，不是 ZIP 缓存。
默认 `--max-archive-mib 128`，可设置 4～4096；预算包含两轮目录清单估算、固定缓冲及 BytesIO 扩容余量，所以 ZIP 可用字节小于这个数字。大量空文件也可能先触发清单预算。`archive_buffer_allocated_bytes` 是实际 BytesIO 分配，memory_budget_bytes 是打包预算估算，**都不等于整个解释器/二维码进程树 RSS**；不设置系统内存、虚拟内存或其他程序限制。
超限明确失败，无磁盘回退；OOM 也给出简短失败。需要更大 ZIP 时由用户显式提高预算并保证可用 RAM，不自动提额。超限测试用 4 MiB 预算和不可压缩样本，未填满机器内存。

静态符号链接、Junction、Windows reparse point 和循环目录拒绝，不读取链接目标的文件内容。Windows 逐文件读取时使用不跟随最终 reparse point 的句柄并核对真实路径归属、身份及状态，拒绝已有写入句柄；打包前后重新遍历、二次 SHA256 读验并再次检查目录，发现增删改/替换时拒绝发布 ZIP。**这不是 VSS 原子文件系统快照**，请在源目录静止时操作；源数据快照完成后播放只读 RAM，不继续访问正在变化的目录。
失败后保留原始文件，默认 play/info 不创建目录/日志，export 不覆盖已有目录。目录输入时 PNG 输出及显式 --log 路径必须在源目录之外（包含路径别名的实际解析检查），否则拒绝，避免改变源目录并污染后续补传。所有资源在退出/取消时关闭；并未创建需事后删除的临时 ZIP。

## 6. Codex 实测与开发者复现

当前机器：Windows 11、Python 3.12.13、zlib 编译/运行版本 1.3.1。机器可读数据见 [ENCODER_2100_FOLDER_METRICS.json](ENCODER_2100_FOLDER_METRICS.json)。

标准样本（3 文件、2 子目录、5515 原始字节）：

| 项目 | 实测 |
|---|---|
| Folder Content MD5 | `5EB77EABFC97A9AD463F887DE488B43B` |
| Folder Content SHA256 | `51EC5522628B3783B04B2801C031EFFF68068CF1483CBDB40F109DA75CD68B2A` |
| Archive ZIP MD5 | `091CBC0DA2451228DC0639285BC6E72F` |
| Archive ZIP SHA256 | `3C165759597FEA5188BC03F4419439A725C204AB2514D3EA0C2386C17B421F1E` |
| ZIP 大小/分包 | 5991 bytes / 3 DATA，START/FINISH 各一次 |
| 真实 PNG / 合成 MP4 | 5/5、5/5 独立 ZXing 成功，ZIP 字节一致，内存解压逐项一致 |
| ZIP 多次生成 | 全部字节、MD5、SHA256 一致；补传原编号内容一致 |
| 临时 ZIP 文件 | 0；测试同时禁止全部 tempfile 工厂并检查磁盘目录不变 |

40 MiB 流式样本为 8 MiB 确定性随机数据 + 32 MiB 零数据。实际 ZIP 8424174 bytes，BytesIO 分配 8983321 bytes，打包预算约 12.07 MiB；独立进程耗时 0.694 秒、RSS 峰值 35782656 bytes（约 34.13 MiB），避免二维码库影响该内存数字。**这不是 40 MiB 二维码传输速度**，此规模不生成全部二维码。

最新完整回归 **305 项通过、0 失败、0 跳过，276.80 秒**；Ruff 格式/静态检查通过。普通文件额外 100/100 满载 PNG、7/7 合成 MP4、1 GiB 流式读取及实际 Windows 权限拒绝检查通过；1 GiB 测试没有生成全部二维码，不代表传输速度。原生播放器截图：[首帧等待](assets/encoder2100-folder/ready.jpg)、[FINISH 保留](assets/encoder2100-folder/finished.jpg)。
空目录、隐藏/空文件、中文/空格/逗号/特殊字符/EXE、时间修改、搬迁根目录、增删改/改名、打包中修改及恢复 mtime、目录表/ZIP 双预算、取消、只读句柄、真实 CLI 与错误补传摘要均由测试覆盖。
Windows 实际 Junction/循环链创建并拒绝验证通过；当前机器创建文件符号链接返回 WinError 1314，未改变系统权限，以链接模式拒绝单测覆盖该分支，**不宣称真实文件 symlink 创建验收通过**。
原生 OpenCV 窗口已自动验证目录首帧等待、5 帧全序列、FINISH 保持至 Esc；诊断显式启用日志，正常默认仍无播放日志。截图是桌面预览，合成 MP4 不是 Windows 截图工具真实录屏；物理录屏/设备识别率仍不冒充通过。

下面只供维护者复现，不要求用户重做：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '测试依赖安装失败' }
$evidence = Join-Path $repo ('temp\folder2100-reproduce-' + [guid]::NewGuid().ToString('N'))
$pytestRoot = Join-Path $repo ('temp\folder2100-pytest-' + [guid]::NewGuid().ToString('N'))
$previousBlas = $env:OPENBLAS_NUM_THREADS
$previousOmp = $env:OMP_NUM_THREADS
try {
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:OMP_NUM_THREADS = '1'
    uv run --no-sync ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw '格式检查失败' }
    uv run --no-sync ruff check .
    if ($LASTEXITCODE -ne 0) { throw '静态检查失败' }
    uv run --no-sync pytest -q --basetemp "$pytestRoot"
    if ($LASTEXITCODE -ne 0) { throw '测试失败，请保留日志' }
    uv run --no-sync python scripts/encoder2100_folder_acceptance.py --root "$evidence"
    if ($LASTEXITCODE -ne 0) { throw '独立验收失败，请查看 report.json' }
    Get-Content -LiteralPath (Join-Path $evidence 'report.json') -Encoding UTF8
} finally {
    $env:OPENBLAS_NUM_THREADS = $previousBlas
    $env:OMP_NUM_THREADS = $previousOmp
}
```

脚本只在全新独占目录创建原始样本、测试 MP4 和报告，不保存 ZIP 文件，不删除其他数据。Windows Python CI 在完整回归之外运行普通文件与文件夹两类独立验收，并上传 report.json、合成 MP4 等证据；精确提交结果见 [本分支源码 CI](https://github.com/yunfei00/qrft/actions/workflows/ci.yml?query=branch%3Afeature%2Fencoder-cli-2100)。
