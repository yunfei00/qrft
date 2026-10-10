# QRFT — 二维码二进制文件传输与视频恢复系统

**当前状态：协议原型与工程骨架，尚未完成可运行产品。** 目标交付日期：2026-10-16（7 天紧凑排期）。

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

## 四个 Windows 程序

1. `QRFT-Encoder-CLI.exe`：命令行编码和二维码显示。
2. `QRFT-Encoder-GUI.exe`：PySide6 图形编码器。
3. `QRFT-Decoder.exe`：无界面分布式视频解码节点。
4. `QRFT-Control.exe`：Web 管理中心、调度、缺包统计和文件恢复。

## 环境与部署

- Python 3.12，**统一使用 uv** 管理虚拟环境、依赖和锁文件。
- Windows 局域网；中心机保存可能达到数十 GB 的录屏文件。
- 工作节点通过 SMB 共享按逻辑时间片读取原视频，不整体上传、复制或物理切片。
- 恢复文件必须通过完整哈希校验，缺包列表可直接用于补传。

## 协作原则

**GitHub 是唯一事实来源，不依赖 ChatGPT 聊天记录。** 任何需要用户亲自操作的任务，必须先写入 [USER_ACTIONS.md](docs/USER_ACTIONS.md)，聊天中只需提示按照对应操作编号执行。能够通过 CI 自动验证的工作不要求用户重复操作。

本仓库公开，请勿提交真实令牌、生产配置、录屏或业务文件。

## 许可证

尚未选择许可证；公开可见不代表自动授予使用许可。
