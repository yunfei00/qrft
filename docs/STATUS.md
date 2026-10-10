# QRFT 项目进度与交接记录

## Phase 3：0.3.0rc1 五程序候选版已交付

[Release 下载](https://github.com/yunfei00/qrft/releases/tag/v0.3.0-rc.1)。第五程序 QRFT-Acceptance.exe 提供中文后台验收、取消、实时日志、三种 SMB 角色配置、资源采样和 HTML/JSON/CSV 报告；原四 EXE 职责与 v1 协议不变。

**117 项测试通过**，Ruff 格式/静态检查通过。PR #5 在七项 CI 全绿后合并；软件构建 Commit **0ccc140b41cd3d41399825ba2fdada6d7904e196**，其 main 七项 CI 及标签两个交付 CI 均成功。下载标签构件后 1080 个文件校验匹配，实际原生 Qt 启动与干净中文目录真实 EXE 验收通过：默认 8 项 PASS、0 FAIL；单 Worker、双 Worker、missing.txt 补传、503 重试/续租/异常退出/过期重领均最终 SHA256 一致。独立合成 AVI 解码及错误 Token/实例隔离通过。

实际开发冻结 GUI 连续 600 秒、3195 帧无错误；实际 Acceptance EXE 1GiB 文件哈希 1.378 秒、采样峰值约 46MiB。严格区分哈希、合成 AVI 与真实录屏传输。详细 Commit、CI、ZIP SHA256 和可追溯报告见 [交付证据](ACCEPTANCE_RESULTS.md)，操作见 [一键验收手册](ACCEPTANCE_RUNNER.md)。

原里程碑仍 **7/10**。真实双 Windows/SMB 与断线重连、录屏、大视频、完整大文件二维码链路、30/60 分钟 GUI、全新无 Python 实机尚未验收，按 USER_ACTIONS.md 的 UA-008 完成。旧 0.2.0rc1 Release 与下方历史记录保留。

**更新日期：2026-10-10**  
**当前阶段：0.2.0rc1 候选版已发布；以下旧记录保留为历史证据**
**目标交付：2026-10-16**  
**产品状态：四个 EXE 已构建且通过实际链路验证；候选版可下载，完整现场验收未完成。当前事实见 FINAL_DELIVERY.md。**

PR #3 已在六项 CI 全绿后合并，软件构建提交 **ce516d4d422c4bb655f7fbf28f770046de63601b**。main 六项 CI 全绿；版本标签交付运行 **38040936148** 全绿。候选版 [v0.2.0-rc.1](https://github.com/yunfei00/qrft/releases/tag/v0.2.0-rc.1) 已发布，包含四个 EXE、运行库、文档和全文件 SHA256 清单。

本地 **104 项测试通过，无跳过**，Ruff 格式与静态检查通过；实际浏览器管理、下载及恢复通过。下载产物的 **801 个文件 SHA256 全部匹配**；本机普通环境与仅 Windows 系统 PATH 的环境均通过四 EXE 完整链路。开发提交 aa255d3、00e473a、6a928b2、3a731a2、b1dc357、56a910c。真实性能结果见 PERFORMANCE.md；软件/协议限制及现场未验收项见 FINAL_DELIVERY.md。

## 已提交 GitHub

- 公开仓库 `yunfei00/qrft`。
- 一周排期、架构、协议草案、验收标准和中文操作手册。
- `pyproject.toml`、`.python-version`（3.12）、uv 开发指南。
- `src/qrft/` 四模块目录和共享核心目录。
- `.github/workflows/ci.yml` Windows CI 配置。
- `src/qrft/core/protocol.py`：START/DATA/FINISH、8 位 ASCII 包号、CRC32。
- `src/qrft/core/manifest.py`：流式 MD5/SHA-256、分块读取、缺包列表解析。
- `tests/test_package.py`、`tests/test_protocol.py`、`tests/test_manifest.py`。
- 项目说明及开发文档已统一为中文。

## 尚未验证/尚未完成

- `uv.lock` 尚未生成并提交；CI 尚未确认通过。
- 真实二维码图像的原始字节往返、录屏识别、缺包恢复尚未实现。
- CLI、GUI、Web 控制端、分布式 Decoder、四个 Windows EXE 尚未完成。
- 真实大视频性能与多机验证尚未开展。

## 下一步（按顺序执行）

1. 使用 uv 生成 `uv.lock` 并提交，CI 改为 `uv sync --locked`。
2. 修复 Windows CI 中的依赖、格式和测试问题，记录运行证据。
3. 实现真实二维码的原始字节生成与读取测试，冻结协议。
4. 完成 CLI 编码器与单机视频解码/缺包恢复闭环。
5. 再开发 Web 控制、分布式节点、GUI 和 Windows 打包。

## 用户操作规则

所有需要用户执行的命令必须先写入 [USER_ACTIONS.md](USER_ACTIONS.md)。当前 **UA-001 为可选的本地环境验证**，没有必须立即执行的用户操作。

## 交接约定

新开发者或新会话先读 README、STATUS、ROADMAP、ARCHITECTURE、PROTOCOL、USER_ACTIONS。每个阶段必须记录：提交文件/Commit、测试命令和 PASS/FAIL、阻塞问题、下一项具体工作。不得用聊天记录代替 GitHub 文档。

## 最新代码提交：缺包导出核心
- 新增 `src/qrft/core/missing.py`：按包总数与已收到包号生成缺包列表，并同时输出 `missing.txt`、`missing.csv`、`missing.json`。
- 新增 `tests/test_missing.py`：覆盖重复包、无缺包、越界包号、TXT 可直接回传编码端解析。
- **验证状态：代码已提交，测试尚未实际执行；不得视为通过。**
- 下一步仍是生成 uv.lock、验证 Windows CI 和真实二维码原始字节往返。

## CI 故障修复记录（2026-10-10）
- 用户反馈：GitHub Actions CI 全部失败。
- 已修复一处明确的工程配置风险：CI 原先执行 `uv sync --all-extras --group dev`，将尚未实现的 GUI/视频解码/控制端全部可选依赖强制安装；现在改为 `uv sync --group dev --no-default-groups`，先验证共享核心和单元测试，避免重型可选依赖阻塞核心 CI。
- CI 仍保留 Ruff 格式检查、静态检查和 pytest，没有取消质量门禁。
- **尚未取得失败作业日志，也未确认本次修复后 CI 通过。** 如果新运行失败，必须读取失败步骤日志，定位并修复实际根因。
- `uv.lock` 尚未提交；后续需要由 uv 生成并启用 `--locked`。

## 功能进度看板（每次功能提交必须更新）

> 统计口径：按以下 10 个交付里程碑计算，每项仅在**实现且验证通过**后计入完成率。代码已提交但未验证不算完成；避免主观百分比。

**软件验收：7 / 10（70%）**。从用户提供的 1/10 基线按原条件逐项补充证据；真实录屏、双设备 SMB、大视频三项仍未通过。最后候选版提交须保持 CI 全绿方可交付，不能将此比例理解为所有 Phase 的每项要求均已完成。

| 里程碑 | 状态 | 验收条件 |
|---|---|---|
| 1. uv 工程与 Windows CI | 通过：锁文件及 3a731a2 六项 CI | uv.lock 已提交、CI 全绿 |
| 2. 二进制帧协议与分块 | 通过：核心/ZXing 原始字节往返 | 测试与真实二维码字节往返通过 |
| 3. 缺包导出与补传格式 | 通过：测试及浏览器 TXT 下载 | TXT/CSV/JSON 测试通过 |
| 4. CLI 编码器 | 通过：真实 Qt/EXE 播放、范围/补传测试 | 可显示二维码并选择补传包 |
| 5. 视频解码与文件恢复 | 合成 AVI 通过，待真实录屏验收 | 真实录屏恢复 SHA-256 一致 |
| 6. Web 控制端 | 通过：浏览器创建/登记/恢复/下载及 API/Worker 状态测试 | 任务/节点/视频/恢复管理可用 |
| 7. SMB 分布式节点 | 单机双 EXE 通过，待双 Windows/SMB | 双 Windows 节点读取同一视频 |
| 8. PySide6 GUI | 通过：GUI 复用 CLI 协议，实际 Qt PNG 经 ZXing 回读 | GUI 与 CLI 互通 |
| 9. 四个 Windows EXE | 通过：实际启动与完整冻结程序链路 CI | 打包并完成启动测试 |
| 10. 端到端可靠性验收 | 模拟故障/补传通过，待大视频实测 | 重传、故障恢复、大视频实测 |

### 最新 CI 排障
- 用户再次反馈 CI 失败。已提交 `5f6c3f1`：在缺少 `uv.lock` 时关闭 `setup-uv` 缓存，避免缓存依赖文件匹配失败造成整条流水线提前中断。
- 当前无法获取具体失败运行的 job ID 和日志；**CI 仍为未验证，不能宣称修复完成**。如继续失败，优先根据 Actions 失败日志定位实际错误，不要删除测试。
- 后续每完成一个功能必须同步更新此进度看板、测试证据、下一步及用户操作手册。

### CI 精确故障定位与修复（运行 38021211028）
- 已通过 GitHub Actions 作业日志确认：Python 3.12 安装成功、uv 依赖安装成功；失败步骤为 `uv run --no-sync ruff format --check .`。
- Ruff 报告 3 个文件格式不符：`manifest.py`、`missing.py`、`protocol.py`。已按照日志差异修复并提交。
- 静态检查与 pytest 在该运行中被跳过，**尚未验证通过**；最新提交触发的 CI 也尚未确认结果。
- **里程碑统计不变：0/10 已验收（0%）；2 项已实现待验证。** 只有新 CI 全绿后才能更新已验收比例。
- CI 证据：https://github.com/yunfei00/qrft/actions/runs/38021211028

### CI 运行 38021294255：已读取真实日志并修复
- 运行地址：https://github.com/yunfei00/qrft/actions/runs/38021294255
- 已通过：Checkout、uv 安装、Python 3.12 安装、核心测试依赖安装、Ruff 格式检查（23 个文件符合格式）。
- **实际失败原因**：Ruff 静态检查在 `src/qrft/core/missing.py` 检出 I001（导入顺序）和 UP035（`Iterable` 应来自 `collections.abc`）。
- 已按 Ruff 诊断修改导入顺序和来源；修复提交 `f32b0a7`。
- 该运行的 pytest 被跳过；**新 CI 尚未验证通过**。
- 交付进度维持 **0/10 验收完成（0%）**，2 项核心功能代码已实现待验证。下一步读取新 CI 的 pytest 结果，若失败按日志修复。

### 用户确认 CI 已通过；进入二维码编码功能（2026-10-10）
- 用户反馈上一轮 Windows CI 已通过；未在本轮独立读取通过作业的 ID 和日志。
- 新增 `src/qrft/core/qr_image.py`：使用 `qrcode.util.QRData` 强制 `MODE_8BIT_BYTE`，将完整二进制协议帧编码成 PNG，不转 Base64 或 UTF-8 文本；容量溢出报错。
- 新增 `tests/test_qr_image.py`：测试含全部 0–255 字节的二进制帧生成 PNG、输入类型及边框校验。
- Windows CI 新增 encoder 可选依赖安装和二维码 PNG 测试步骤；新提交尚未验证通过。
- **进度：1/10 已验收（10%，按用户反馈 CI 通过计），协议与缺包模块仍为已实现待验证，二维码 PNG 生成模块已实现待验证。**
- 重要：PNG 可生成并不等于已验证扫码后字节一致；下一步必须接入 `zxing-cpp` 原始字节读取进行往返测试。

### 本轮：CLI 二维码帧导出及指定缺包补传（2026-10-10）
- 用户确认上一轮 CI 已通过。
- 新增 `src/qrft/encoder_cli/main.py`：提供 `python -m qrft.encoder_cli.main 文件 --output 目录 [--chunk-size 256] [--retransmit missing.txt]`；流式生成 START、DATA、FINISH PNG 帧和 JSON 清单。
- 新增 `tests/test_encoder_cli.py`：覆盖二进制分包、中文文件名、指定缺包补传和空文件。
- Windows CI 新增 CLI 测试；**本轮新 CI 尚未确认通过**。
- 这是 **PNG 帧导出子功能**，还不具备全屏播放、暂停、预生成缓存、真实视频解码和 EXE 打包，不能把 CLI 里程碑算作验收完成。
- **里程碑进度维持 1/10（10%）**；新增 CLI 导出子功能为已实现待验证。
- 下一步：二维码原始字节往返验证、实时播放和端到端文件恢复。

### 本轮：真实二维码图像原始字节往返（2026-10-10）
- 新增 `src/qrft/core/qr_decode.py`：使用 ZXing-C++ 识别 PNG，取 `result.bytes` 原始字节，交给 QRFT CRC32/包号校验；不通过文本解码。
- 新增 `tests/test_qr_roundtrip.py`：覆盖空包、0x00/0xff/非 UTF-8、完整 0–255 字节、START 中文及 Emoji 元数据、FINISH、无法识别的图片。
- Windows CI 新增真实 ZXing 二维码往返步骤，并安装 encoder+decoder 依赖。
- **本轮提交尚未取得 CI 结果**；若 ZXing 对原始字节或输入格式存在平台差异，必须按真实 CI 日志修复。
- **总体验收进度仍为 1/10（10%）**；新增二维码解码子功能已实现待验证。下一步为真实录屏视频读取与文件恢复闭环。

### 本轮：文件恢复核心（2026-10-10）
- 新增 `src/qrft/core/reassemble.py`：START 清单验证、乱序 DATA 随机写入、重复包内容一致性检查、FINISH 标记、缺包 TXT/CSV/JSON 导出、SHA256+MD5 校验后输出原始文件。
- 新增 `tests/test_reassemble.py`：乱序及重复包恢复、缺包导出、冲突重复包和非法长度校验。
- 当前实现为单次内存状态恢复器，**不支持跨进程断点恢复**；尚未接入视频逐帧读取、SQLite 和分布式调度。
- **新 CI 尚未确认通过；里程碑维持 1/10（10%）**。

### CI 故障复盘：运行 38022567444
- 实际作业日志：https://github.com/yunfei00/qrft/actions/runs/38022567444
- Python、依赖安装均通过；`ruff format --check .` 在 `src/qrft/core/reassemble.py:99` 失败（Ruff 要求哈希比较条件为单行）。
- 已按 Ruff 日志中的精确格式改回单行；修复提交 `a835bc4`。
- 静态检查、pytest、图片测试、ZXing 测试均因格式检查失败被跳过，不能声称这些检查已通过。
- **验收进度维持 1/10（10%）**，待新 CI 验证。

### 本轮：视频读取与本地恢复入口（2026-10-10）
- 用户确认上一轮 CI 已通过。
- 新增 `src/qrft/decoder/video.py`：OpenCV 从本地/可访问 SMB 路径直接读取视频，按 FPS 和时间范围取帧；ZXing 从帧提取原始 QR 字节并进行 CRC 校验。
- 新增 `src/qrft/decoder/main.py`：`python -m qrft.decoder.main VIDEO --output DIR [--sample-fps 10] [--start 0] [--end N]`，将帧接入文件恢复核心。
- 新增 `tests/test_video_decoder.py`：模拟视频帧的端到端文件恢复、参数边界验证。
- **本轮 CI 尚未确认**；尚无真实录屏视频验收，视频随机定位性能、丢帧容错、分布式租约和断点续传仍待实现。
- **验收进度维持 1/10（10%）**，不将模拟测试视作真实视频验收。

### 本轮：真实 AVI 视频自动化端到端测试（2026-10-10）
- 用户确认上一轮 CI 通过。
- 新增 `src/qrft/encoder_cli/video_export.py`：将 START/DATA/FINISH PNG 帧重复写入 MJPG AVI 视频，作为自动化验收输入（不是最终实时全屏播放器）。
- 新增 `tests/test_video_end_to_end.py`：生成真实 AVI 视频文件，使用 OpenCV 读帧、ZXing 识别原始字节、重组文件，并断言全部原始字节一致。
- Windows CI 增加真实 AVI 视频闭环测试，**本轮新 CI 尚未确认通过**；若发生二维码失真、帧尺寸或采样问题须按日志修复。
- **里程碑仍为 1/10（10%）**，在 CI 和实际录屏验收通过前不增加验收进度。

### 本轮：编码端全屏实时播放（2026-10-10）
- 用户确认真实 AVI 端到端 CI 已通过。
- 新增 `src/qrft/encoder_cli/playback.py`：按需生成 START、DATA、FINISH 帧，支持 TXT 缺包补传列表，避免预生成全量二维码。
- 新增 `src/qrft/encoder_cli/player.py`：PySide6 全屏/窗口播放，初始延迟、播放间隔、空格暂停/继续、Esc 退出；命令入口 `python -m qrft.encoder_cli.player`。
- 新增 `tests/test_playback.py`：帧顺序、原始二进制内容、指定缺包补传测试；无图形界面依赖。
- **本轮 CI 尚待验证，且真实 Windows 全屏显示尚待人工验收**；尚未实现有限队列并行预生成、开始/结束包号范围控制、最终 EXE。
- **里程碑仍为 1/10（10%）**，不将代码提交等同于验收。

### CI 修复：运行 38025301123（2026-10-10）
- 读取实际 Actions 作业日志，确认仅 `src/qrft/encoder_cli/playback.py:30` 的 Ruff 格式检查失败：`yield` 二元组需要显式括号和换行。
- 按日志精确修改，提交 `018591e`。
- 后续静态检查、单元测试及视频测试均被跳过，需等待新运行验证；总验收进度保持 1/10（10%）。

### 本轮：播放包号范围控制（2026-10-10）
- 用户确认上一轮 CI 通过。
- `iter_encoded_frames` 新增 `start_id` / `end_id`（闭区间），与缺包列表求交集，仍保留 START/FINISH 控制帧。
- 全屏播放器 CLI 新增 `--start-id` 和 `--end-id` 参数。
- 新增范围、补传交集、无效边界及空文件测试。
- 本轮代码已提交，**新 CI 尚未验证**；总体验收仍为 **1/10（10%）**。
- 下一步：有限预生成队列、播放器性能与 Windows EXE 打包。

### CI 修复：运行 38027663752（2026-10-10）
- 读取 Actions job 114141852198 日志，定位 `src/qrft/encoder_cli/playback.py:35` 的 Ruff 格式问题。
- 严格按 Ruff 日志将 `parse_packet_list(...)` 列表推导式调用改为单行，修复提交 `db2a8e8`。
- 静态检查、pytest、二维码及 AVI 测试均被格式门禁跳过；新 CI 尚待验证。总体验收仍为 1/10（10%）。

### 本轮：有界并行二维码预生成队列（2026-10-10）
- 用户确认上一轮 CI 已通过。
- 新增 `src/qrft/encoder_cli/prefetch.py`：`ThreadPoolExecutor` 并行生成 PNG，`capacity` 限制待处理帧数量，按原始包号顺序消费，迭代结束时关闭线程池。
- 全屏播放器接入预生成器，新增 `--workers`（默认 2）及 `--prefetch`（默认 4）参数。
- 新增 `tests/test_prefetch.py`：保序、容量限制、参数边界测试。
- 本轮 CI 尚未验证；真实 Windows 图形播放流畅度、线程退出及长视频性能尚待实测。
- **总体验收进度仍为 1/10（10%）**；下一步继续完善播放器错误处理、打包与 Windows 验收。

### CI 故障修复：运行 38030878716（2026-10-10）
- 直接读取 GitHub Actions 作业日志：格式检查通过，Ruff 静态检查失败，其他测试跳过。
- I001：`src/qrft/encoder_cli/player.py` 导入顺序错误；修复提交 `33d5ccd`。
- UP047：`src/qrft/encoder_cli/prefetch.py` 泛型函数需使用 Python 3.12 类型参数语法；修复提交 `7a387a5`。
- **新 CI 结果尚未确认**；验收进度保持 1/10（10%）。
- 工作流程：后续主动读取 CI 运行及失败日志，能自动完成的操作不要求用户手动提供。

### 本轮：播放器生命周期修复（2026-10-10）
- 读取 main 最新提交；GitHub connector 的 `fetch_commit_workflow_runs` 只返回 PR 触发运行，因此当前无法由该接口确认最新 push CI 状态，未宣称通过。
- 修复开始延迟期间暂停后定时器行为；恢复时立即继续，避免额外等待。
- 播放完成后禁止空格重新启动，正常完成、二维码错误、预生成异常及关闭窗口时关闭预生成迭代器并释放线程池。
- 启动前校验 `workers/prefetch` 参数。
- 本轮提交 `bb5ddb2`，新 CI 尚待验证；验收仍为 1/10（10%）。

### CI 故障修复：运行 38031158790（2026-10-10）
- 从 GitHub Actions job 114152203232 读取完整日志：格式检查通过，静态检查因 `player.py:81` 的 Ruff BLE001 失败；后续测试未运行。
- 将宽泛的 `except Exception` 收窄为 `except (OSError, RuntimeError, ValueError)`，保留用户可见错误提示。
- 修复提交 `25209bd`；新 CI 尚待验证，总体验收保持 1/10（10%）。

### 本轮：Windows Encoder CLI EXE 构建流水线（2026-10-10）
- 用户确认上一轮 CI 通过。
- 新增 `src/qrft/encoder_cli/entrypoint.py`：统一 `export` 与 `play` 子命令。
- 新增 `.github/workflows/build-encoder.yml`：Windows Python 3.12 + uv + PyInstaller onedir 打包 `QRFT-Encoder-CLI.exe`，执行 `--help`、真实小文件 PNG 导出冒烟测试，并上传构件。
- 新增 `tests/test_encoder_entrypoint.py`：命令入口测试；缺少 encoder 可选依赖时跳过。
- **新构建 CI 尚未验证；未宣称 EXE 已生成或可运行**。总体验收进度保持 1/10（10%）。

### Windows Encoder EXE #4 故障修复（2026-10-10）
- 读取运行 `38031704104`、作业 `114153840706` 的真实日志：PyInstaller 构建成功，`--help` 冒烟测试因 Windows 控制台 `cp1252` 无法编码中文而抛出 `UnicodeEncodeError`，上传构件步骤跳过。
- `entrypoint.py` 在 CLI 入口配置 stdout/stderr 的 `backslashreplace` 编码错误处理，避免不可表示字符导致崩溃；构建工作流的冒烟测试显式设置 `PYTHONIOENCODING=utf-8`。
- 修复提交 `c802d1c`、`3e7b582`；新构建运行尚未验证，不能声称 EXE 已通过冒烟测试或已上传。
- 总体验收进度仍为 1/10（10%）。

### 本轮：第二个 Windows EXE（Decoder）打包（2026-10-10）
- 用户确认 Windows Encoder EXE 上轮 CI 已通过；本轮未独立读取该通过作业的日志。
- 新增 `.github/workflows/build-decoder.yml`：Windows + uv + Python 3.12，先运行真实 AVI 端到端恢复测试，再用 PyInstaller 打包 `QRFT-Decoder.exe`，运行 `--help` 冒烟测试，成功后上传 `QRFT-Decoder-windows` 构件。
- `docs/USER_ACTIONS.md` 新增 UA-002：构件下载、保留 `_internal`、Windows 本地验证及视频恢复验证指引。无需现在人工操作。
- **Decoder 构建 CI 尚未验证**；四个 EXE 中仅推进到第二个，未完成 GUI/Control，也未验收双节点 SMB 分布式解码。
- 总体已验收仍为 **1/10（10%）**，待对应里程碑全部达到验收标准再调整。

### Decoder EXE CI 失败修复（运行 38032036288，2026-10-10）
- 从作业 `114154815475` 的日志确认：真实 AVI 视频端到端回归测试 PASS，PyInstaller 打包 PASS，EXE `--help` 冒烟测试 FAIL。
- 根因：冻结后的 Windows 程序使用 `cp1252` 输出中文帮助，抛出 `UnicodeEncodeError`；仅设置 `PYTHONIOENCODING` 未能解决。
- 修复：在 `src/qrft/decoder/main.py` 的 CLI 入口对 stdout/stderr 配置 `backslashreplace` 错误处理，提交 `2a6ce6b`。
- 新一轮 CI 尚未验证；仍为 1/10（10%）已验收。

### 本轮：PySide6 图形编码器实现及 Windows EXE 构建（2026-10-10）
- 用户确认上一轮 Decoder EXE CI 通过。
- 新增 `src/qrft/encoder_gui/main.py`：源文件/导出目录/缺包 TXT 选择，分包大小、播放间隔、启动延迟配置，PNG 导出与全屏播放按钮，调用现有 CLI 共享核心。
- 调整 `encoder_cli/player.py`：GUI 中播放复用既有 QApplication 事件循环，避免嵌套 `app.exec()`；保留播放窗口引用。
- 新增 `.github/workflows/build-gui.yml`：PyInstaller 构建 `QRFT-Encoder-GUI.exe`，验证构件存在并上传。
- **本轮 GUI 的 CI 尚未验证；GUI 实际 Windows 启动/交互亦未验收**。现阶段 GUI 导出在主线程运行，大文件可能阻塞界面，后续应迁移后台工作线程。
- 总体验收仍为 1/10（10%）；下阶段先修复新 CI，再完善 GUI 异步处理及 Control 端。

### Windows Python CI 运行 38032313905 修复（2026-10-10）
- 实际作业日志：格式检查 FAIL，Ruff 指出 `encoder_cli/player.py:127` 单引号以及 `encoder_gui/main.py:108` 条件表达式多行格式；其余 42 个文件格式通过，后续静态检查/测试未执行。
- 按 Ruff 给出的精确修改修复两处格式：提交 `edcb791`、`3d106e4`；不涉及业务逻辑变更。
- 修复后的 CI 尚未确认；总体验收维持 1/10（10%）。

### 本轮：Control 控制中心基础 API（2026-10-10）
- 用户确认 GUI 阶段 CI 已通过。
- 新增 `src/qrft/control/app.py`：FastAPI `/health`、带 Bearer Token 鉴权的任务创建/列表、视频路径登记/列表、节点心跳/列表；SQLite WAL 持久化。
- 新增 `tests/test_control_api.py`：鉴权、任务视频关系、心跳幂等、SQLite 重连持久化；Windows CI 添加 control 可选依赖与 httpx 测试。
- 当前服务默认仅绑定 `127.0.0.1:8787`；通过 `QRFT_API_TOKEN` 配置鉴权，未配置时保护接口返回 503。
- **未实现**逻辑时间片调度、租约、二进制包接收、缺包合并、Web 管理页面及 Control EXE 打包；本轮 CI 尚未验证，不能计入里程碑 6 完成。
- 总体验收保持 1/10（10%）。下一步先修复/确认 CI，再补时间片与租约调度。

### CI 运行 38032665745 修复（2026-10-10）
- 实际日志确认 Windows Python CI 在 Ruff 格式检查失败，45 个文件已格式化，唯一问题文件 `tests/test_control_api.py` 两处跨行 assert 表达式。
- 已按 Ruff 输出精确修改并提交 `55bcb72`。静态检查、pytest、Control API 测试在失败运行中均未执行；新 CI 结果待验证。
- 验收进度保持 1/10（10%）。

### 两次 Windows Python CI 静态检查失败修复（2026-10-10）
- 运行 `38032797339` 和 `38032801239` 均已核实：Ruff format 通过，Ruff check 因 `tests/test_control_api.py` 两处未启用的 `# noqa: E402` 触发 `RUF100` 失败；后续测试被跳过。
- 已移除两处无效 noqa 并提交 `39ae1c6`。用户反馈其余 CI 通过；此修复后的新 CI 尚待验证。
- 里程碑验收维持 1/10（10%）。

### 本轮：Control 时间片调度和租约机制（2026-10-10）
- 用户确认上一轮 CI 通过。
- 新增 `src/qrft/control/scheduler.py`：默认 30 秒切片/1 秒重叠、SQLite 唯一约束去重、BEGIN IMMEDIATE 原子领取、租约超时重领、归属检查、幂等完成。
- `src/qrft/control/app.py` 在登记视频时自动生成切片，提供 `POST /slices/claim`、`POST /slices/{slice_id}/complete`、`GET /slices`（均需 API Token）。
- 新增 `tests/test_scheduler.py`，覆盖切片覆盖范围、重复登记、租约到期重领、归属检查与完成幂等。
- **本轮尚未通过 CI**；节点实际解码、租约续期、结果包批量上传与恢复尚未实现。验收仍为 1/10（10%）。

### 本轮：租约续期与原始 QR 数据包批量接收（2026-10-10）
- 用户确认上一轮 CI 通过。
- `scheduler.renew`：仅当前有效租约持有者可以续期；原子事务保证状态一致。
- 新增 `control/packets.py`：解码原始 QRFT DATA 帧并验证 CRC，SQLite 按 (task_id,packet_id) 去重，冲突数据写入 packet_conflicts 隔离表。
- `control/app.py`：新增 `POST /slices/{slice_id}/renew`、`POST /packets/batch`、`GET /packets/{task_id}/stats`；受 Token 保护，限制每批包数和单包字节数。
- 新增 `tests/test_control_packets.py`，覆盖去重、冲突、损坏包拒绝、续期归属与完成状态。
- **本轮尚未验证 CI**。当前批量接口在部分包成功后遇到错误时可能保留先前包；下一轮需增强整批原子性、START 会话绑定、缺包导出及解码节点联动。
- 验收进度仍为 1/10（10%）。

### 本轮：START 会话绑定、批量事务、缺包查询（2026-10-10）
- 用户确认前一轮 CI 通过。
- 新增 `POST /tasks/manifest`：绑定并验证 START 元数据，拒绝不一致的重复绑定和已存在数据包后的绑定。
- `POST /packets/batch`：整批 SQLite IMMEDIATE 事务；失败时通过 connection 上下文回滚；绑定 manifest 时验证包号和 payload 长度。
- 新增 `GET /tasks/{task_id}/missing`：返回总包数、已接收数和缺包 ID 列表。
- `tests/test_control_api.py` 新增 API 回归测试：批量失败不留部分数据、缺包计算和完整接收。
- **本轮 CI 尚待验证**；尚未实现 START/FINISH 帧从视频节点自动提交、缺包文件导出及恢复。验收保持 1/10（10%）。

### 本轮：分布式 Worker 初版（2026-10-10）
- 用户确认上一轮 CI 通过。
- 新增 `src/qrft/decoder/worker.py`：无界面 Worker，HTTP Token 认证、心跳、领取时间片、按范围直接扫描可访问 SMB 视频、批量提交 QRFT DATA 帧、完成租约。
- `scheduler.claim` 返回 `task_id`，使 Worker 提交到正确任务。
- 新增 `tests/test_worker.py`：模拟视频帧与控制端，覆盖时间片范围、批次提交、心跳及领取流程。
- **当前限制**：Worker 尚未实现扫描期间续租、START 不在当前时间片时的可靠会话引导、FINISH 标记、请求失败重试和真实双机 SMB 验收；不能标记分布式里程碑完成。
- **本轮 CI 尚待验证；总验收仍为 1/10（10%）。**

## 接管与分布式可靠性阶段（2026-10-10）

- 基线 main `af1ac2e`，工作区干净，分支 `feature/distributed-decoder-reliability`。
- CI 38035201954 真实日志：两个模拟 videos 表缺 task_id；Worker 测试硬编码 Unix 路径。均修复，未删除测试。
- uv 安装 Python 3.12.13；生成 uv.lock；正式声明 httpx，CI 安装全部依赖并使用 --locked。
- Worker 独立心跳/续租线程、HTTP 暂态错误指数退避、Ctrl+C 清理、FINISH 提交；失败不完成租约，等待到期重领；同节点有效租约期间禁止继续分配。
- DATA 可以先于 START 持久化，绑定时校验已有包号和长度；FINISH 持久化，START 冲突拒绝。
- 增加任务进度、恢复状态、缺包导出和恢复 API；从 SQLite 流式重建临时文件，CRC32/SHA256/MD5 校验后原子发布，拒绝覆盖和 Windows 非法文件名。
- 中断后可以重新从 SQLite 重建；尚未实现复用临时文件的增量恢复。缺包集合与已收包号集合仍占与包数相关的内存，大文件性能待实测。
- v1 DATA/FINISH 没有会话 ID：不同来源同长度包不能由单包鉴别；START 冲突、包冲突隔离和最终哈希防止静默输出错误文件，不能声称彻底解决串包。协议升级需兼容方案。
- 生成 AVI 测试不等于真实录屏或真实双 Windows SMB 验收。Web 管理入口已补齐任务/视频登记、进度/节点/时间片查看、缺包导出和恢复；四 EXE 完整交付、大视频性能尚未验收。
- 本地 Windows Python 3.12.13：Ruff format/check PASS；pytest **82 passed，无跳过**（7.31s）；二维码/ZXing/AVI/Control/Worker 专项 **31 passed**（4.50s）；全部关键依赖导入 PASS。Starlette/httpx 弃用警告 1 条，非失败。
- 本机旧 pytest 临时目录 ACL 拒绝访问，使用 `PYTEST_DEBUG_TEMPROOT=D:/code_2026/qrft/temp` 后全部通过；没有修改用户临时目录权限。环境下载通过 NO_PROXY=* 绕过本机慢代理，Python 原版归档由 uv 安装。
- 修改文件：pyproject.toml、uv.lock、ci.yml、control/app.py、control/recovery.py、control/scheduler.py、decoder/worker.py、core/reassemble.py、相关测试与文档。
- 功能提交 `fc98925`，PR #1；Windows CI [38036564566](https://github.com/yunfei00/qrft/actions/runs/38036564566) 已全绿。
- 后续补充 Web 管理入口、报告/临时文件同名恢复回归、[14 类测试覆盖说明](DISTRIBUTED_TESTING.md)。最终验证记录随提交补充。总验收基线保持 **1/10（10%）**。
- 新增 Decoder EXE 的 worker 子命令并保留本地恢复；新增 Control EXE 构建、HTTP 服务/任务 API/Web 登录页面冒烟流水线。构建成功不等于真实设备验收。
- 最终本地门禁：58 个 Python 文件格式通过、Ruff check PASS、**90 passed，无跳过**（8.35s）；Web JavaScript `node --check` PASS；Control/Decoder worker 帮助启动 PASS。最终 PR CI 与构件结果将在推送后记录。
- 第二阶段提交 `20405da`：[Windows CI 38036835026](https://github.com/yunfei00/qrft/actions/runs/38036835026) 全绿，90 passed（11.35s），图片 6 passed，ZXing 6 passed，真实 AVI 1 passed，Control/Worker 集成 27 passed，无跳过。
- [Control EXE 38036835057](https://github.com/yunfei00/qrft/actions/runs/38036835057) 构建、EXE 帮助、真实 HTTP health/任务创建/Web 页面冒烟和构件上传全部通过。
- [PR #1](https://github.com/yunfei00/qrft/pull/1) 的最终文档提交 `c96c372` 通过两项检查后于 2026-10-10 16:12（上海）正常合并，main 为 `da8c5f8`；未强推或绕过检查。
- main 的五条流水线全部成功：[Python CI](https://github.com/yunfei00/qrft/actions/runs/38037055366)、[Encoder CLI](https://github.com/yunfei00/qrft/actions/runs/38037055399)、[Encoder GUI](https://github.com/yunfei00/qrft/actions/runs/38037055433)、[Decoder](https://github.com/yunfei00/qrft/actions/runs/38037055365)、[Control](https://github.com/yunfei00/qrft/actions/runs/38037055384)。四个 onedir 构件已上传。
- EXE 自动化证据：Encoder CLI 帮助/PNG 导出；Decoder 本地/worker 帮助；Control 帮助/真实 HTTP health、创建任务及 Web 页面；GUI 仅构件存在检查，尚无实际交互验收。Python 全量仍为 90 passed，无跳过。
- 下一步：UA-006 实际双设备与 SMB 故障验收；兼容现有协议的会话 ID 扩展设计、包数内存优化、增量临时文件恢复、真实录屏/大视频性能和四 EXE 人工启动验收。当前验收仍为 1/10。
