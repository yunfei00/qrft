# QRFT 更新日志

## 尚未发布

### 正式交付开发（PR #3）
- 新 Worker HTTP 租约代次围栏、持久扫描检查点、一秒重扫重叠及重新扫描 API；保留 v1 与旧 HTTP 客户端兼容。
- 系统概览、配置说明、重复计数及节点处理状态；交付测试增加两个 Worker EXE 并发及 CLI 自动播放。
- GUI 后台检查、PNG 导出、共享有界播放器、暂停/继续/停止、范围和缺包补传。
- 缺包分页、流式 TXT/CSV/JSON 下载、SQLite 流式恢复；Web 表格和在线节点概览。
- 任务取消、Worker JSON 配置及环境变量 Token、顺序视频采样。
- 锁定经启动验证的 PySide6 6.9 系列；四个 EXE 构建纳入 PR 门禁。
- 可重复性能脚本；真实双机、SMB、录屏与长时间稳定性仍待人工验收。

### 工程与文档
- 初始化公开 GitHub 仓库及一周交付计划。
- 确定四个交付程序、Windows 局域网和 SMB 分布式视频解码架构。
- 建立 uv 工程骨架、Python 3.12 版本约束和 Windows CI 工作流。
- 统一中文文档，新增用户操作手册，所有人工步骤必须先入库。

### 核心协议原型
- 实现 DATA/START/FINISH 二进制帧和 CRC32 校验。
- 实现文件分块、MD5/SHA-256 计算、指定包列表解析。
- 新增协议与文件分块单元测试，**尚未验证 CI 结果**。

**未完成：** uv 锁文件、真实二维码往返、视频解码、Web 控制、GUI 和 EXE 打包。

### 缺包管理
- 新增缺包列表 TXT/CSV/JSON 导出核心，TXT 格式与补传包号解析器兼容；已提交测试但尚未验证执行结果。

### 编码器 CLI 子功能
- 新增二进制文件流式二维码 PNG 帧导出，支持 `--chunk-size` 和 `--retransmit`，导出 START/FINISH 控制帧及 manifest.json。
- 新增 CLI 导出、缺包重传和空文件测试；新 CI 尚待验证。

### 真实二维码往返
- 新增 ZXing-C++ PNG 二维码识别，严格提取原始字节并复用协议 CRC 校验。
- 新增二进制数据与控制帧往返测试并纳入 Windows CI；尚待 CI 验证。

### 分布式可靠性（2026-10-10）

- Worker 心跳续租、HTTP 退避、安全中断；START 延迟绑定及 FINISH 持久化。
- SQLite 文件恢复、缺包文件导出和任务进度 API；最终哈希校验及拒绝覆盖。
- 修复 Windows 路径测试和模拟表结构，生成 uv.lock，锁定完整依赖 CI。
- 实际测试和 CI 证据见 docs/STATUS.md，验收比例保持 1/10。
- 新增 Web 管理入口；Decoder EXE 暴露 worker 子命令；Control EXE 构建和 HTTP 冒烟验证。
