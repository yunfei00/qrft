# QRFT

通过二维码和录屏传输文件，核心流程是 **编码 → 视频解码 → 合并恢复**。

| 程序 | 职责 |
|---|---|
| Encoder CLI | 命令行编码文件或文件夹、导出二维码、播放和缺包补传 |
| Decoder | 桌面界面导入视频、扫描、查看缺包和合并恢复 |
| Control | 网页调度中心，管理任务、视频、节点、进度和恢复结果 |

仅保留 v2 协议和一套编码实现 `encoder_cli`。默认 **2100 字节/包**，编码时可用 `--chunk-size` 调整（1–2124）；START 携带实际分块大小，解码端自动读取。文件夹先在内存中打包成确定性 ZIP，恢复后不自动解压。

## 安装

Python 3.12，使用 uv 管理依赖：

```powershell
uv sync --locked --all-extras --group dev
```

只运行编码端可用 `uv sync --locked --no-dev --extra encoder`；解码桌面端用 `--extra decoder`，独立调度中心用 `--extra control`。

## 编码：只有 CLI

研发阶段暂时关闭编码端口令匹配和交互终端限制，无需输入口令，可直接从命令行或脚本运行。`src/qrft/encoder_cli/access.py` 的 `PASSWORD_CHECK_ENABLED = False` 控制此临时行为；发布时可恢复为 `True`。这不影响调度中心的 API Token。

```powershell
# 不带参数或使用 --help 查看总帮助；子命令也支持 --help
uv run --no-sync python -m qrft encode --help
uv run --no-sync python -m qrft encode play --help

# 默认 2100 字节；文件和文件夹都可作为输入
uv run --no-sync python -m qrft encode info "D:\Data\example.bin"
uv run --no-sync python -m qrft encode play "D:\Data\example.bin"

# 自定义分块，或导出 PNG
uv run --no-sync python -m qrft encode play "D:\Data\ExampleFolder" --chunk-size 1400
uv run --no-sync python -m qrft encode export "D:\Data\example.bin" --output "D:\QRFT\frames"

# 使用缺包清单补传，分块大小须与首次传输一致
uv run --no-sync python -m qrft encode play "D:\Data\example.bin" --missing "D:\QRFT\project\reports\missing_packets.txt"
```

`play` 的窗口仅显示供录屏的二维码；Space 开始、暂停或继续，Esc 结束。没有编码设置 GUI。文件夹补传还须提供首次 `info` 输出中的 `--expected-archive-md5`，防止源目录改变。

## 解码和合并

```powershell
# 打开桌面界面：创建任务、导入同文件的视频和补传视频、开始解码、查看缺包、恢复
uv run --no-sync python -m qrft decode

# 也可对项目目录批量操作：录屏放入 PROJECT/videos
uv run --no-sync python -m qrft decode "D:\QRFT\project"

# 只合并项目已解出的包，不再扫描视频
uv run --no-sync python -m qrft merge "D:\QRFT\project"
```

项目目录批量模式在 `state/` 保存续跑状态，`reports/missing_packets.txt` 保存缺包清单，`reports/decode_result.json` 保存结论，恢复文件放在 `output/`。同一文件的多个录屏、补传录屏放进同一个项目后再次解码即可；已成功且未改变的视频会跳过。

桌面界面通过本地 Control/Worker 管理解码，也可以连接已有调度中心。它的任务数据保存在所选工作目录的 `.qrft-decoder/` 中，与批量项目目录分别使用。

## 调度中心界面

```powershell
$env:QRFT_API_TOKEN = Read-Host 'API Token'
uv run --no-sync python -m qrft control
```

打开 [调度中心](http://127.0.0.1:8787/)，输入同一 Token。创建任务后登记视频路径；分布式节点需要能直接读取同一路径（可使用只读 SMB 共享）：

```powershell
uv run --no-sync python -m qrft worker --server http://CENTER:8787 --node-id worker-1
```

节点通过 `QRFT_API_TOKEN` 环境变量读取 Token。调度中心合并各节点收到的包、导出缺包清单，并在整文件 MD5 一致后发布恢复文件。不同文件必须分开任务；同包号不同内容会阻止恢复。

## 开发和打包

```powershell
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync python scripts/build_windows.py
```

Windows 只打包三个程序：`QRFT-Encoder-CLI`、`QRFT-Decoder`、`QRFT-Control`。完整复制对应目录，不能只复制 EXE。

核心说明：[协议](docs/PROTOCOL.md)、[架构](docs/ARCHITECTURE.md)、[开发](docs/DEVELOPMENT.md)。当前整理后的协议使用含分块大小的 START；历史三字段 START 和 QRFT2100 标记格式不再兼容，旧录屏应使用对应旧版本恢复。

尚未选择许可证；公开可见不代表自动授予使用许可。
