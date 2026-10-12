# QRFT 系统架构

2026-10-12 v2开发补充：共享protocol_v2与validation，Frame保留版本及原始线字节；编码/Qt/OpenCV/PNG复用相同二维码生成器。Control任务协议锁及兼容SQLite迁移，Worker不重编码线帧；本地导入也使用持久包表、START绑定与流式恢复核心。v2无file_size/SHA256/文件ID字段，末包决定长度、最终MD5校验，未知来源视频须明确任务关联。OpenCV采用带GUI的opencv-python；decoder仍无界面运行，避免与headless两个发行包争用cv2。


## 当前实现补充（0.3.0rc1）

原四程序保留职责，新增第五个独立 `QRFT-Acceptance.exe` 作为验收编排器，通过实际 EXE/鉴权 HTTP API 测试，不复制协议实现。当前视频读取为 OpenCV + ZXing 原始字节解码；控制中心使用 FastAPI、SQLite BLOB 包存储和原生中文 HTML/JavaScript 页面，没有 React 前端。以下初期选型记录保留为历史；实现以 src/qrft 为准。一键验收与现场范围见 ACCEPTANCE_RUNNER.md，v1 DATA 无会话 ID 的来源限制仍存在。

QRFT 传输的是**任意二进制文件**，不依赖文件扩展名或文本编码。

## 四个交付程序

1. `QRFT-Encoder-CLI.exe`：命令行编码器，文件分块、二维码全屏显示、指定包重传。
2. `QRFT-Encoder-GUI.exe`：PySide6 本地图形编码器，复用公共编码核心。
3. `QRFT-Decoder.exe`：无界面的 Windows 解码节点，注册、心跳、领取时间片、读取视频、批量提交结果。
4. `QRFT-Control.exe`：内置 Web 服务和管理界面，任务调度、结果合并、文件恢复与缺包导出。

## 处理流程

编码器读取文件原始字节并显示二维码；外部录屏软件生成视频；中心机注册已有视频文件路径，不经浏览器上传整个大文件；调度器划分**逻辑时间片**；解码节点通过只读 SMB 共享直接读取对应视频范围，使用 FFmpeg 按关键帧定位、裁剪二维码区域并识别帧；节点批量上传包数据；中心机使用 SQLite 记录元数据、磁盘文件保存二进制包，去重并校验后恢复原文件。

## 可靠性要求

- 编码器和解码器均使用有界内存，不整体加载文件或录屏。
- 时间片边界重叠，防止二维码跨边界丢失；按包号去重。
- 任务租约超时重试，节点断线可恢复，批量结果幂等提交。
- 同一包号不同内容进入冲突隔离区，不能静默覆盖。
- START 元数据绑定会话，来源不明的数据不得直接合并。
- 每次解码尝试生成 `missing.txt`、`missing.csv`、`missing.json`。
- 只有全部包齐全且整体哈希一致，才标记恢复成功。

## 安全和性能

公开仓库不提交真实令牌、录屏、业务文件、内网地址。SMB 共享最小权限，工作节点使用 API 令牌。实际性能必须测量 CPU、内存、磁盘、SMB 网络与每秒有效包数。

## 技术选型

Python 3.12 + uv；pytest；PySide6；FastAPI；FFmpeg/ffprobe；需通过原始字节验证的二维码库；React；PyInstaller onedir；GitHub Actions Windows CI。
