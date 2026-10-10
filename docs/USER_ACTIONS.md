# QRFT 用户操作手册（唯一操作入口）

**约定：所有需要用户执行的操作，必须先写入本文件，再在聊天中提示“请按照 [用户操作手册](USER_ACTIONS.md) 的 UA-XXX 执行”。** 命令统一使用 Windows PowerShell，确保可复制。每项必须写明执行时机、环境、命令、预期结果和反馈方式。CI 能自动完成的事情不要求用户重复执行。

## UA-001：Windows 本地 uv 环境验证

**状态：待执行；仅在需要本机复现或 CI 失败时执行。当前无需操作。**

环境：已安装 Git 和 uv 的 Windows PowerShell。uv 安装指南：https://docs.astral.sh/uv/getting-started/installation/

```powershell
git clone https://github.com/yunfei00/qrft.git
cd qrft
uv python install 3.12
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

预期：自动建立 `.venv`；测试和静态检查通过。若失败，反馈出错命令及完整输出；成功则反馈 `UA-001 PASS`。

## UA-002：真实二维码录屏验证

**状态：暂不需要。** 编码器完成后，将在这里补充录屏软件设置、示例文件、操作命令、预期哈希及反馈格式。

## UA-003：Windows 局域网 SMB 分布式解码验证

**状态：暂不需要。** 工作节点和控制端完成后，将在这里补充共享权限配置、节点命令、测试数据与预期结果。不得提交真实密码或令牌。

## UA-004：四个 Windows EXE 验收

**状态：暂不需要。** 打包完成后，将在这里补充下载地址、四个程序的启动命令及验收标准。

## 状态维护

执行完成后在 GitHub 记录：执行日期、命令、PASS/FAIL、日志位置。未验证不得标为通过。

### UA-005：提供失败的 GitHub Actions 运行链接（仅当无法自动定位最新运行时）
**状态：待用户提供运行链接。**

前提：`yunfei00/qrft` 的 Windows Python CI 出现红色失败。

1. 打开 https://github.com/yunfei00/qrft/actions 。
2. 点击最上方标记红色叉号的 **Windows Python CI** 运行记录。
3. 从浏览器地址栏复制完整地址，格式为 `https://github.com/yunfei00/qrft/actions/runs/数字`，发送到当前对话。

预期：得到包含数字 run ID 的链接；助手即可直接读取该次运行的失败步骤和完整日志，修复根因，不需要用户复制大量日志或本地运行命令。

## UA-002：Windows 编码器/解码器构件下载与基础验收（可选，构建成功后执行）

1. 打开仓库 GitHub Actions，选择成功的 **Windows Encoder EXE** 或 **Windows Decoder EXE** 运行。
2. 在运行页面的 **Artifacts** 下载 `QRFT-Encoder-CLI-windows` 或 `QRFT-Decoder-windows`；分别解压到不同目录。**必须保留整个解压目录（含 `_internal`），不能只复制 EXE。**
3. 在 PowerShell 进入编码器目录，运行：

   ```powershell
   .\\QRFT-Encoder-CLI.exe --help
   .\\QRFT-Encoder-CLI.exe export C:\\Temp\\sample.bin --output C:\\Temp\\qrft-frames
   ```

   其中 `C:\\Temp\\sample.bin` 替换为本机真实存在的小文件。检查输出目录中的 `manifest.json` 和 PNG 图片。
4. 在解码器目录运行 `.\\QRFT-Decoder.exe --help`，检查帮助文字是否正常显示。
5. 视频恢复实际验收需要一段包含完整 START/DATA/FINISH 的二维码录屏：

   ```powershell
   .\\QRFT-Decoder.exe C:\\Temp\\qrft-recording.avi --output C:\\Temp\\qrft-restored
   ```

   录屏必须真实存在；程序输出成功并核对 SHA-256 后才算视频恢复验收通过。尚未准备录屏时可跳过第 5 步。

> UA-002 为构件成功后可选的本地人工验收；当前 CI 可自动完成编码器 PNG 导出冒烟测试、解码器帮助启动测试及真实 AVI 端到端 Python 回归测试，无须现在执行。

## UA-006：真实双 Windows / SMB 验收

状态：待外部设备；模拟测试不替代本项。两台节点须能读取中心机同一只读 SMB 共享，防火墙允许控制端端口。

中心机设置测试 Token、数据库和恢复目录并启动控制端：

```powershell
$env:QRFT_API_TOKEN = Read-Host '测试 API Token'
$env:QRFT_DB_PATH = 'C:\Temp\qrft-control.sqlite3'
$env:QRFT_OUTPUT_DIR = 'C:\Temp\qrft-recovered'
uv run --no-sync uvicorn qrft.control.app:app --host 0.0.0.0 --port 8787
```

在 /docs 页面设置 Authorization Header，通过 POST /tasks 创建任务，通过 POST /videos 登记任务 ID、UNC 视频路径和真实时长。每个任务只登记同一原始文件的录屏与补传视频，v1 DATA 没有文件 ID，不可混用文件。

两台节点分别运行，替换 SERVER 和各自唯一 NODE_ID：

```powershell
$token = Read-Host '测试 API Token'
uv run --no-sync python -m qrft.decoder.worker --server http://SERVER:8787 --token $token --node-id NODE_ID
```

检查 /nodes、/slices、/tasks/{task_id}/progress。长片扫描时确认心跳及续租；中途 Ctrl+C 退出一个节点，等待 120 秒租约到期后确认另一台接管。断网后恢复，确认重试和已收包持久化。无效共享路径必须报错且不得标记 done。

调用 POST /tasks/{task_id}/missing/export，返回目录包含 missing.txt、missing.csv、missing.json；使用 missing.txt 执行编码端 --retransmit，再登记补传视频到同一任务。调用 POST /tasks/{task_id}/recover：

```powershell
Get-FileHash 'C:\Temp\original.bin' -Algorithm SHA256
Get-FileHash 'C:\Temp\qrft-recovered\TASK_ID\original.bin' -Algorithm SHA256
```

预期哈希相同；再次恢复返回 409，既有文件不覆盖。记录 Windows 版本、节点 ID、视频时长、包统计、故障重领和哈希证据，反馈 UA-006 PASS/FAIL。当前无真实双机验收结果。
