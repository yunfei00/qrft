# 正式交付开发记录

基线：main 58acb5f，已独立核对五条 Windows CI 全部成功，90 项测试基线。工作区干净，分支 feature/qrft-final-delivery。v1 二维码字节协议保持不变。

剩余清单：GUI 非阻塞文件检查/导出、共享播放器完整控制；Web 表格与下载/设置；取消/租约围栏/扫描进度/配置文件；流式缺包与恢复、视频顺序扫描；真实并发端到端测试；四 EXE 功能冒烟及统一带校验清单的 Release；部署、维护和排障文档。

## Phase A

- GUI 后台哈希和 PNG 导出；文件信息、纠错/像素、包范围、补传、开始延迟、暂停/继续/停止和全屏切换。
- CLI 与 GUI 共用真实播放器；有界后台 PNG 队列、包号/进度/剩余时间，退出时释放线程和文件。
- 缺包选择外部 SQLite 排序/合并区间，避免展开范围；编码持有一个文件流连续读取，PNG 导出以独占创建保护已有文件。
- 真实 Qt 自动化覆盖中文文件检查、PNG 经 ZXing 回读、暂停/继续/完成、缓存容量和启动延迟退出；GUI EXE 增加真实 Qt 自动启动/退出测试。
- 本地/提交/CI 结果按实际执行更新；真实 GUI 交互和双机 SMB 不以 offscreen 测试代替。

## 后续开发与验证

- Phase A 提交 aa255d3，Python CI 通过；GUI EXE 启动门禁实际发现 Qt 6.12 DLL 问题。改为锁定 PySide6 6.9.3 后本机无控制台 EXE 创建窗口并退出，exit=0。
- 缺包 API 默认返回最多 1000 个 ID，支持 after/limit 游标和 missing_count；完整下载支持鉴权 TXT/CSV/JSON 流式生成，不接受任意下载路径。
- 控制中心恢复按 SQLite 排序游标写入并校验 CRC/SHA256/MD5，不加载全部包号。断电后从持久化 SQLite 重新恢复，暂未实现跳过已写磁盘区块的恢复检查点。
- Web 增加节点概览、视频/时间片表格和下载。任务取消停止调度并拒绝 DATA 提交。Worker 可用 JSON 配置及 QRFT_API_TOKEN 环境变量，避免在命令行暴露 Token。
- 视频采样一次定位后顺序读取；新增 scripts/benchmark.py 与 scripts/windows_smoke.py。统一交付工作流执行四 EXE 的真实 PNG→AVI→解码→HTTP Worker→SQLite→文件哈希链路。
- 租约围栏、持久化扫描检查点、完整中文状态展示/设置和长期 GUI 稳定性尚未完成；不得标记这些要求已交付。

## 性能实测（Windows 本机）

运行：`uv run --no-sync python scripts/benchmark.py --output temp/benchmark-1g.json`。
真实写入并读取 1,073,741,824 字节文件，哈希 2.82 秒，Python 分配峰值 2,106,646 字节。
10 万包号中实际写入 SQLite 5 万个 256 字节数据包，1.53 秒；导出 5 万缺包的三份报告 1.40 秒，Python 分配峰值 376,165 字节。
这些是本机一次运行结果，不能代表原生 RSS、完整 1GB 二维码传输、大视频、SMB 或真实多机吞吐。
