# QRFT 项目进度与交接记录

**更新日期：2026-10-10**  
**当前阶段：Phase 0 工程初始化 / Phase 1 协议原型**  
**目标交付：2026-10-16**  
**产品状态：尚无可运行的四个 EXE，未完成端到端验收。**

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

**已验收：0 / 10（0%）**；**已实现待验证：2 项**。

| 里程碑 | 状态 | 验收条件 |
|---|---|---|
| 1. uv 工程与 Windows CI | 待验证 | uv.lock 已提交、CI 全绿 |
| 2. 二进制帧协议与分块 | 已实现，待验证 | 测试与真实二维码字节往返通过 |
| 3. 缺包导出与补传格式 | 已实现，待验证 | TXT/CSV/JSON 测试通过 |
| 4. CLI 编码器 | 未完成 | 可显示二维码并选择补传包 |
| 5. 视频解码与文件恢复 | 未完成 | 真实录屏恢复 SHA-256 一致 |
| 6. Web 控制端 | 未完成 | 任务/节点/视频/恢复管理可用 |
| 7. SMB 分布式节点 | 未完成 | 双 Windows 节点读取同一视频 |
| 8. PySide6 GUI | 未完成 | GUI 与 CLI 互通 |
| 9. 四个 Windows EXE | 未完成 | 打包并完成启动测试 |
| 10. 端到端可靠性验收 | 未完成 | 重传、故障恢复、大视频实测 |

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
