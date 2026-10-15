# V2 / QRFT2100 单机项目视频解码

本轮入口是 **`python -m qrft decode 项目目录`**，单进程、无 GUI、无 Control/Worker/API Token。支持当前独立编码器 QRFT2100（2100 字节）和已有旧 V2（1400 字节），不新增 V1 解码逻辑，不改变编码器或已发布线协议。旧 GUI/分布式入口保留供历史系统使用，不自动读取其数据库。

## 1. 环境与最简操作

使用 Windows PowerShell；CMD 同样可执行 uv/python 命令。首次获取代码可用 `git clone https://github.com/yunfei00/qrft.git D:\code_2026\qrft`；已有仓库先保护未提交修改，再切换/同步 main，不覆盖本地工作。

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
git status --short
git fetch origin
git switch main
if ($LASTEXITCODE -ne 0) { throw '请先保护本地修改' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw '同步失败' }
uv python install 3.12
uv sync --locked --python 3.12 --no-dev --extra encoder --extra decoder
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
$project = 'D:\QRFT\project001'
New-Item -ItemType Directory -Path (Join-Path $project 'videos') -Force | Out-Null
```

把**同一个原文件/目录传输任务**的视频放入 `$project\videos`。文件名不要求连续，可含中文、空格，程序不从文件名推断包号。然后运行：

```powershell
uv run --no-sync python -m qrft decode "$project"
$decodeExit = $LASTEXITCODE
Get-Content -LiteralPath (Join-Path $project 'reports\missing_packets.txt') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $project 'reports\decode_result.json') -Encoding UTF8
Write-Host "Decoder exit code: $decodeExit"
```

解码入口不需要编码器口令。成功输出 `MD5: PASS`、`Result: SUCCESS`，文件在 `output` 下；只有已知元数据、完整有效包、无冲突、传输 MD5 和适用的文件夹指纹全部通过才成功。FINISH 缺失不阻止包完整且 MD5 正确的恢复。

退出码：0=SUCCESS，2=INCOMPLETE 或 FAILED（看 JSON 区分），130=中断，1=项目/数据库/路径等入口错误。**非零退出不表示恢复成功**；入口错误未能更新报告时，不要把上一次报告当作本次结果，核对 completed_at。

## 2. 项目结构与扫描规则

```text
project001/
  videos/                         # 递归读取同一任务的视频
  state/
    OWNER.txt                     # 自有状态标记；不接管无标记的旧目录
    run.lock                      # 系统文件锁，防止同时运行两个解码进程
    project.db                    # SQLite：视频、唯一包字节、来源、元数据、输出记录
    decode.log                    # 详细帧错误与扫描失败
  reports/
    missing_packets.txt           # 全量缺包编号，可直接补传
    decode_result.json            # 当前运行结果、计数、哈希、错误及相对输出路径
  output/
    原文件名或文件夹名.zip
```

数据包使用 SQLite BLOB，不额外创建 packets 目录。`packets` 每个包号/内容 SHA256 组合只保存一份真实字节；`receipts` 独立记录各来源视频和首次时间；同号不同内容保留两个版本并阻止恢复，不静默覆盖。`observations` 是只读关联视图。状态使用本模块独立的 schema，不兼容旧 Control/GUI 数据库，发现不支持的数据库版本会拒绝运行。

支持 mp4/avi/mov/mkv/m4v/wmv/webm/mpg/mpeg/mts/m2ts（实际可读取编解码器以本机 OpenCV 为准）。除递归扫描 videos 外，也扫描**项目根目录直接放置的视频文件**，不递归根目录其他文件夹，不扫描 output/state/reports。稳定按相对路径 UTF-8 排序；包按线上编号合并，视频排序不改变编号。项目中链接、Junction、循环目录拒绝，避免访问范围外的数据。

全部可迁移状态和输出路径都位于项目内，数据库的视频路径、报告的输出路径为相对路径。停止程序后可整体移动项目目录；移动后使用新项目路径运行，不需要改数据库。

## 3. 续跑、重试与视频变化

重复执行同一条 decode 命令即可续跑：

- 已 completed 且大小/mtime/SHA256 未变的视频跳过**二维码解码**；仍流式读取 SHA256 以识别保留相同大小/mtime 的替换，不等于再次扫描视频。
- 新增、failed 或上次崩溃留下 processing 的视频从头重扫，复用已提交的有效包。
- 每 25 帧将包和进度一起提交 SQLite（WAL、synchronous=FULL）；Ctrl+C 安全退出，最后未提交的一小批帧重扫。进程硬退出后系统释放独占锁，下一次继续，不伪造 completed。
- 源视频变化或删除时撤销其来源记录，只有不再有其他有效来源的包才清理；扫描中变化也撤销该视频已提交来源。不会继续无条件信任旧 completed 状态或旧包。
- 单帧无二维码/识别失败不退出整个任务；损坏、打不开或可检测到的提前 EOF 记 failed，继续其他视频。解码器无法保证发现容器未声明帧数的所有截断；最终依靠包完整性/MD5，不能只看 completed。

`completed` 只表示视频完整扫描，不代表原文件恢复成功。一个无二维码视频也可能 completed；缺 START/缺 DATA 的项目仍是 INCOMPLETE。冗余损坏视频并不必然阻止其他视频提供全部正确字节，因此 SUCCESS 时仍可能有 videos_failed，需要查看 video_errors。

要主动重扫未变化的 completed 视频（如更换识别库后），使用：

```powershell
uv run --no-sync python -m qrft decode "$project" --rescan
```

不要删除数据库来补包，不需要重做已成功视频。源视频/项目被其他程序占用、项目已有解码进程或无法写入时，先解决占用再重试；不会自动修改权限或删除用户数据。

## 4. 缺包补传

missing_packets.txt 的统计头以 `#` 开头，后面输出**全部**缺失的八位十进制编号（0 起），没有截断到前后若干包；无缺包时仍有 `# Missing packets: 0`。无可信 START 时写明 UNKNOWN，不假定包完整。

当前独立 EXE 编码器的文件夹补传必须使用**初次发送任务的 Archive ZIP MD5**，不是 Folder Content MD5。将实际路径替换到下面变量；源码编码器也可以使用同样参数：

```powershell
$encoder = 'D:\Tools\QRFT-Encoder2100\QRFT-Encoder2100.exe'
$original = 'D:\Data\ExampleFolder'
$missing = Join-Path $project 'reports\missing_packets.txt'
$originalArchiveMd5 = Read-Host '粘贴原任务 Archive ZIP MD5（32位HEX）'
& $encoder play "$original" --missing "$missing" --expected-archive-md5 $originalArchiveMd5
```

每次启动编码器仍手动隐藏输入 `qsnfj`、Enter，Space 开始/暂停/继续，Esc 关闭，录制完整固定白色区域与静区。保存补传视频到**原项目** videos 目录，再执行原 decode 命令。普通文件补传不传 expected-archive-md5；原文件/分块/编号必须不变。旧 1400 字节 V2 任务必须用旧 V2 编码器补传，不能混入 QRFT2100。

同号冲突或不同 START 元数据时为 FAILED，不自动挑一个“看起来正确”的版本。根据 state/decode.log 和 SQLite receipts 来源隔离错误视频，再运行；不同原文件请新建项目，既有项目锁定元数据，不自动切换任务。

## 5. 两种 MD5、协议边界与安全输出

线上具体定义见 [QRFT2100 协议](ENCODER_2100_PROTOCOL.md) 和 [旧 V2 协议](PROTOCOL.md)。两种 START 都没有原始文件大小、文件 ID 或 SHA256 字段；本入口不擅自添加字段：

- 从 START 锁定真实协议、文件名、传输 MD5、总包数和对应 2100/1400 字节分块。
- `task_id` 是项目内部按元数据确定性计算的 SHA256，不冒充线上文件 ID。DATA 无来源 ID，视频必须由用户明确放入同一项目；陌生无 START 视频的来源不能仅凭 DATA 自证。
- `wire_file_size=null` 如实表示线上没有该字段；非末包严格要求整块，末包决定恢复字节数，actual_size 是实际流式恢复大小，不凭空制造“期望大小”。
- START 的 MD5 校验**实际传输字节**，目录就是 ZIP MD5。普通文件传输本身是任意二进制字节，不按扩展名解释文件类型。
- 恢复出的 ZIP comment 若为 QRFT2100-FOLDER-1，则按目录/路径/长度/原始内容的规范序列流式重算 Folder Content MD5 和 SHA256，含根及空目录；与 Archive ZIP MD5 分开记录，不能相互替代。

只有包、MD5 及适用的文件夹指纹全部通过才发布最终文件。先写本项目新建 `.part`，fsync、验证后以**不覆盖目标的原子硬链接**发布（Windows 本地 NTFS 支持）；不支持该操作的文件系统会报错，不降级为可能覆盖用户文件的写法。已有非本项目输出拒绝；本项目之前输出只有内容仍与记录一致才复用。中断可能留下自有 `.part`，不当成恢复成功，不自动删除未知文件；再次运行可从数据库重组。

恢复目录 ZIP 后**不会自动解压**；只验证并输出 ZIP，用户可在单独目录解压。文件夹验证默认最多 8 GiB 解压后字节，逐块读、零磁盘解压；按需要显式提高 `--max-folder-bytes`，超限为 FAILED，不跳过指纹检查。MD5 不是防恶意篡改的认证机制。

## 6. 自动测试与边界

不要求用户重复 Codex 已完成的自动测试。维护者可运行实际源码验收脚本：

```powershell
Set-Location 'D:\code_2026\qrft'
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '开发依赖安装失败' }
$evidence = Join-Path (Get-Location) ('temp\single-decoder-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync python scripts/single_decoder_acceptance.py --root "$evidence"
if ($LASTEXITCODE -ne 0) { throw '验收失败，请保留 acceptance.json' }
Get-Content -LiteralPath (Join-Path $evidence 'acceptance.json') -Encoding UTF8
```

脚本真实调用 Source、二维码生成、OpenCV MP4、ZXing、多视频项目、缺包补传和 CLI，不用 mock 替代关键链路。37 项专门测试另外覆盖旧 V2 实际 AVI、任意二进制、空文件/空目录、中文/特殊名称、单帧多码、重复/冲突、最终 MD5 错误、目录逻辑指纹错误、中断及进程硬退出、视频替换/扫描中变化、数据库内容损坏、移动项目、锁、输出保护、危险路径与完整缺包编号；仅原生读取异常使用故障注入，确认该视频 failed 后其他真实视频继续恢复。

**自动生成的 MP4/AVI 不是真实 Windows 屏幕录制验收。** 新 QRFT2100 真实录屏识别率、不同显示器/DPI、真实双机/SMB 仍未计为通过；本阶段无多进程/分布式/GUI 开发，不发布新 Release、不打新 Tag。
