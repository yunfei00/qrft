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
