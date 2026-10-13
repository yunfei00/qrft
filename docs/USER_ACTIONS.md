# QRFT 用户操作手册（唯一操作入口）

## UA-011：v2-P9 统一解码 GUI 最终源码验收

**本次 Windows 11 真实录像 GUI 验收从 [P9_REAL_MP4_ACCEPTANCE.md](P9_REAL_MP4_ACCEPTANCE.md) 第 1 步开始。** 这是最终现场验收的唯一逐步执行清单；复用 P8 的原始文件、第一段 MP4 和补传 MP4，完成首段缺包→停止重开→补传→文件 MD5/SHA256 对比。若遇到错误按该文档第 8 步反馈，停止当前环节、不重跑已通过步骤；不要求用户重复 Codex 已完成的自动验收。

**状态：UA-011 真实 Windows MP4 单机 GUI 用户验收 PASS（2026-10-13，依据用户反馈）；另有本地原生 Windows 合成 MP4 自动验收 27 项 PASS。** P8 和 P9 已验收的部分均无需重复执行。真实双 Windows/SMB 与物理断网仍待第二台电脑；P10 大规模/长时验证交给 Codex，执行方案见 [P10_STABILITY_PERFORMANCE_PLAN.md](P10_STABILITY_PERFORMANCE_PLAN.md)。 准备、启动、错误处理和分布式命令统一在 [DECODER_USER_GUIDE.md](DECODER_USER_GUIDE.md) 第 1～8 节。已有 P8 第 1～10 步 PASS 继续有效，不要求重录编码视频。

原生 Qt 自动验收使用真实 PySide6 控件、文件对话框、拖放、Control/Worker 进程及真实生成的 MP4。结果、截图、日志和性能摘要见 [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md)；本机完整证据保存在该记录列出的独占 `temp/p9-native-acceptance-*` 目录。若需人工复核 GUI，按手册第 2 节使用专用临时工作区。真实双 Windows/SMB、物理断网与重连仍需按 UA-006 在第二台电脑执行；本机多个进程不计为双机通过。

自动化报告已覆盖合成 MP4、真实独立 Worker、补传、哈希、租约故障恢复、原生 GUI 稳定性与安全关闭，不要求用户重复已完成的本地检查。合成 MP4 不是 Windows 截图工具录屏；真实多机按手册第 7 节后续执行共享、唯一节点、隐藏 Token、断网/租约重领/重连和 MD5，本机进程不计入该验收。

## UA-010：v2-P8 编码端最终收尾人工验收

**状态：PASS（用户在 ChatGPT 会话中报告 Windows 11 源码第 1～10 步全部成功）。无需重复验收。** 详细执行入口是 [V2_USER_GUIDE.md 的“Windows 11 本地源码验收（uv）”](V2_USER_GUIDE.md)，证据来源、口令重试经过及未提供字段见 [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md)。Codex 未直接访问本次人工验收环境或查阅原始录屏/日志，不将本条反馈扩展为双机 SMB、多屏/DPI 或长时间测试通过。

在 feature/qrft-v2-hex-md5 源码环境按 [V2_USER_GUIDE.md 的“Windows 11 本地源码验收（uv）”](V2_USER_GUIDE.md) 执行。GUI 无口令：文件选择、v2 参数锁定、检查哈希、PNG 导出进度、取消、窗口关闭必须正常；默认不全屏。

在普通交互式 PowerShell 分别启动纯 CLI 和 OpenCV 播放命令：启动后静默等待，没有提示文字，手动输入小写 `qsnfj` 后按 Enter，字符和星号均不可见；大小写敏感，最多三次尝试，失败后非零退出，可重新执行同条命令。CLI 不提供 -h/--help，未知/缺失参数在校验后拒绝；管道/重定向运行应拒绝。GUI 不需要口令，纯 export 只在新目录生成 PNG/清单，不出现 Qt 窗口。

播放器操作：默认固定非全屏窗口，首张 START 静止等待 Space，不自动播放；点击窗口取得焦点后 Space 开始、暂停、恢复，Esc 在窗口/全屏均结束，关闭按钮也能退出。录屏必须包含整个固定白色二维码区域及静区，不仅框选较小的 START；普通与补传布局相同，文字在区域外。录制前可选择全屏，录制期间保持模式、位置、DPI 不变。OpenCV 提前退出可能返回 130，与截图工具是否保存 MP4 独立；按手册检查文件再解码/补传，不以退出码代替录像结果。真实 MP4 首段→missing.txt→补传→同任务合并→MD5 已由用户报告通过；多屏/DPI、长时间测试和真实双机仍待另行验收，双机按 UA-008，不要求重做本次已通过步骤。

## UA-009：QRFT v2 Windows 11 本地源码录屏验收

**状态：第 1～10 步用户报告 PASS；与 UA-010 共用同一份 [人工验收记录](ACCEPTANCE_RESULTS.md)，不是第二次独立验收。** 本项保留为源码流程索引，后续需要复现时再使用详细手册。

**当前推荐方式：用 Python 3.12 + uv 直接运行源码，不使用打包 EXE。** 执行 [V2_USER_GUIDE.md 的“Windows 11 本地源码验收（uv）”](V2_USER_GUIDE.md) 全章；所有源码命令、变量定义、预期结果、失败处理和通过条件均在该节。准备可运行 Windows 桌面、Git、网络、Python 3.12（uv 可自动安装）、uv 和 Windows 11 截图工具。请在同一个 PowerShell 窗口依序执行，保留自动生成的独占 temp 工作目录。

本操作包含真实人工 MP4 录制，本次已由用户反馈通过，不能归因于自动 AVI 测试。具体分支 Commit、显示器/DPI、录像 FPS、哈希数值、日志/截图未提供，不补造这些字段。当前操作仅支持同机本地录像/恢复；真实双机 SMB 仍按 UA-008 单独验收。旧打包 EXE 流程仅作历史参考。


## UA-008：第五程序与真实双机验收

时机：[0.3.0rc1 五程序候选 Release](https://github.com/yunfei00/qrft/releases/tag/v0.3.0-rc.1) 下载后（335,909,638 字节，ZIP SHA256 见 ACCEPTANCE_RESULTS.md）。环境：两台 Windows、可访问 UNC 共享、同版本完整解压目录。按 [中文一键验收手册](ACCEPTANCE_RUNNER.md) 运行单机默认项目并导出完整报告；其结果不替代真实双机。

控制机选择 SMB 控制机 + Worker A，配置可写 UNC 共享和本次 Token，允许局域网端口 8788。Worker B 在另一台 Windows 配置控制机 IP、日志给出的 UNC 视频与同一 Token，开始测试。收集两端报告，检查不同机器标识、不同时间片、最终 SHA256。无第二台电脑时保持“真实双机 SMB：未验收”。基础双机链路成功后，完整 SMB 项目仍 BLOCKED，远程断网/重新连接未自动执行。

进一步人工验收使用 UA-006 的常规控制中心/Worker（独占测试目录），登记真实录屏及较长视频：扫描期间断开 B 的网络、等待租约重新分配、重新连接 B，确认已接收包保留、最终 SHA256 一致；记录每个节点日志、时间片 attempts 和恢复结果。不得对用户生产任务执行取消或 rescan。GUI 选择 10/30/60 分钟稳定性并保存帧数、时长和资源指标；还需人工测试暂停、全屏和关闭。将 Release、系统、视频规模、两端报告、原始/恢复哈希及 PASS/FAIL 一起反馈。自动化合成视频不替代真实录屏。

## UA-007：候选版桌面与设备验收

时机：候选版 Release 发布后；环境：两台 Windows、只读 SMB 共享和录屏软件。按 [运维手册](OPERATIONS.md) 解压完整四程序目录，核对 ZIP 与运行库校验清单，确认无需安装 Python。GUI 选择中文路径文件，分别测试范围/缺包补传、PNG、延迟、暂停/继续/停止、全屏/退出全屏、播放中关闭，连续播放至少一小时并记录内存。用真实录屏执行 UA-006 的双节点、断网、退出/租约重领、补传与哈希核对；记录系统版本、Release、视频规模、各节点日志及 PASS/FAIL。自动化 offscreen 和单机双进程测试不代替这些步骤。

本轮补充：Worker 推荐将 Token 放在 `QRFT_API_TOKEN` 环境变量，JSON 配置只记录 server 和 node_id，用 `QRFT-Decoder.exe worker --config worker.json` 启动。浏览器新增鉴权 missing.txt/CSV/JSON 下载。GUI offscreen 与合成 AVI 自动测试不替代 UA-006 的真实双机/SMB/录屏验收；界面长时间播放、暂停、全屏切换仍需在 Windows 桌面手动确认并记录结果。

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
Get-FileHash 'C:\Temp\qrft-recovered\TASK_ID\files\original.bin' -Algorithm SHA256
```

预期哈希相同；再次恢复返回 409，既有文件不覆盖。记录 Windows 版本、节点 ID、视频时长、包统计、故障重领和哈希证据，反馈 UA-006 PASS/FAIL。当前无真实双机验收结果。

控制端根路径 `/` 提供 Web 管理入口：输入 Token 后连接，创建/选择任务、登记视频、查看进度/节点/时间片、导出缺包及恢复文件。登录页面本身不含业务数据，所有数据请求继续验证 Authorization；Token 不写入浏览器持久存储。`/docs` 保留 API 调试入口。
