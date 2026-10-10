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
