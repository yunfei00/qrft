# QRFT — 二维码二进制文件传输与视频恢复系统

v2-P9 新增统一源码解码 GUI：单机自动管理 localhost Control 和独立 Worker；导入同任务 MP4/AVI、后台扫描、缺包导出、补传合并、哈希恢复；分布式模式复用现有 HTTP/SQLite。运行 `uv run --no-sync python -m qrft.decoder_gui.main`，完整操作见 [源码解码手册](docs/DECODER_USER_GUIDE.md)，最终桌面验收为 [UA-011](docs/USER_ACTIONS.md)。GUI 无编码 CLI 口令，本阶段不打包。

本分支 `feature/qrft-v2-hex-md5` 开发软件0.4.0.dev0：新增v2大写HEX + MD5、固定1400字节、50ms、START/FINISH各20次；v1编码默认及解码兼容保留。见 [v2中文手册](docs/V2_USER_GUIDE.md) 和 [协议](docs/PROTOCOL.md)。本轮仅提交/推送、Draft PR验证，不合并main、不发布Release；下面已发布0.3.0rc1为历史候选版，不支持v2。

v2-P8 编码端推荐按 [Windows 11 本地源码验收（uv）](docs/V2_USER_GUIDE.md) 操作：GUI 无需口令；纯 CLI 先执行本地交互校验，不提供帮助开关，不接受无终端/管道输入。Qt/OpenCV 默认固定窗口，首帧等待 Space，Space 开始/暂停/继续，Esc 结束；文字不进入固定白色录屏区。源码第 1～10 步及真实 Windows MP4 已由用户报告 PASS，见 [UA-010 / UA-009](docs/USER_ACTIONS.md) 和 [人工验收记录](docs/ACCEPTANCE_RESULTS.md)；Codex 未直接查阅其录屏/环境，真实双机 SMB 仍未验收。


**当前状态：Python 编码/视频恢复闭环、控制中心和分布式 Worker 已实现；完整产品与真实双机验收尚未完成。** 目标交付日期：2026-10-16（7 天紧凑排期）。

QRFT 支持将任意二进制文件转换为二维码序列，通过录屏保存，再使用单机或多台 Windows 解码节点从视频中恢复文件。

## 项目文档（全部以 GitHub 为准）

- [最新进度、已验证内容和下一步](docs/STATUS.md)
- [一周开发计划](docs/ROADMAP.md)
- [系统架构](docs/ARCHITECTURE.md)
- [二进制协议草案](docs/PROTOCOL.md)
- [验收标准](docs/ACCEPTANCE.md)
- [uv 开发环境](docs/DEVELOPMENT.md)
- [用户操作手册（可复制命令）](docs/USER_ACTIONS.md)
- [开发规范](CONTRIBUTING.md)
- [更新日志](CHANGELOG.md)

## 五个 Windows 程序

新增第五个独立工具 **QRFT-Acceptance.exe**，提供中文一键验收、真实 EXE 的单机/双 Worker/补传/故障恢复、性能采样与 HTML/JSON/CSV 报告。操作见 [一键验收手册](docs/ACCEPTANCE_RUNNER.md)。0.3.0rc1 五程序候选版已发布，旧 0.2.0rc1 下载仍保留。真实双机 SMB、实际录屏和大视频验收不能由本地模拟代替。

当前候选软件版本 **0.3.0rc1**，新增第五个验收工具。部署、操作、备份、升级和排障见 [Windows 运维手册](docs/OPERATIONS.md)，本轮测试证据见 [一键验收结果](docs/ACCEPTANCE_RESULTS.md)，原四程序的历史证据见 [0.2.0rc1 交付记录](docs/FINAL_DELIVERY.md)。候选版不代表真实双机 SMB 和大视频已验收。

下载入口：[0.3.0rc1 五程序候选版](https://github.com/yunfei00/qrft/releases/tag/v0.3.0-rc.1)。[旧 0.2.0rc1](https://github.com/yunfei00/qrft/releases/tag/v0.2.0-rc.1) 保留。性能方法、结果和未测项目见 [性能报告](docs/PERFORMANCE.md) 与 [一键验收结果](docs/ACCEPTANCE_RESULTS.md)。

1. `QRFT-Encoder-CLI.exe`：命令行编码和二维码显示。
2. `QRFT-Encoder-GUI.exe`：PySide6 图形编码器。
3. `QRFT-Decoder.exe`：无界面分布式视频解码节点。
4. `QRFT-Control.exe`：Web 管理中心、调度、缺包统计和文件恢复。
5. `QRFT-Acceptance.exe`：中文一键验收、故障/补传测试、性能采样及证据报告。

## 环境与部署

- 使用 Release：完整解压五程序目录，无需安装 Python；请勿单独复制 EXE。
- 源码开发：Python 3.12，**统一使用 uv** 管理虚拟环境、依赖和锁文件。
- Windows 局域网；中心机保存可能达到数十 GB 的录屏文件。
- 工作节点通过 SMB 共享按逻辑时间片读取原视频，不整体上传、复制或物理切片。
- 恢复文件必须通过完整哈希校验，缺包列表可直接用于补传。

## 协作原则

**GitHub 是唯一事实来源，不依赖 ChatGPT 聊天记录。** 任何需要用户亲自操作的任务，必须先写入 [USER_ACTIONS.md](docs/USER_ACTIONS.md)，聊天中只需提示按照对应操作编号执行。能够通过 CI 自动验证的工作不要求用户重复操作。

本仓库公开，请勿提交真实令牌、生产配置、录屏或业务文件。

## 本地启动

```powershell
uv sync --locked --python 3.12 --all-extras --group dev
$env:QRFT_API_TOKEN = Read-Host 'API Token'
uv run --no-sync python -m qrft.control.app
```

打开 `http://127.0.0.1:8787/`，输入同一 Token，创建任务并登记节点可访问的视频路径。分布式节点使用 `python -m qrft.decoder.worker --server URL --token TOKEN --node-id NODE_ID`；打包解码器对应 `QRFT-Decoder.exe worker` 子命令，本地视频恢复参数仍兼容。
真实双机步骤、故障验收和哈希验证见 UA-006；测试覆盖与已知协议限制见 [分布式测试说明](docs/DISTRIBUTED_TESTING.md)。

## 许可证

尚未选择许可证；公开可见不代表自动授予使用许可。
