# 正式交付开发记录

## 最终候选版交付

- [PR #3](https://github.com/yunfei00/qrft/pull/3) 在六项 CI 全绿后合并；构建提交 ce516d4d422c4bb655f7fbf28f770046de63601b。
- main Python CI 38040893758、Encoder CLI 38040893727、GUI 38040893732、Decoder 38040893778、Control 38040893748、Windows Delivery 38040893754 全部通过。版本标签交付运行 [38040936148](https://github.com/yunfei00/qrft/actions/runs/38040936148) 通过。
- 实际 EXE：GUI 创建窗口/退出、CLI 播放/PNG 导出、AVI 本地恢复、两个 Worker EXE 并发处理不同时间片、HTTP 控制端、SQLite 合并、SHA256 与原始内容一致。GUI offscreen 与同机双进程不代表真实桌面/双机 SMB 验收。
- 下载上述标签构件后，本机核对 801 个文件 SHA256 全部一致；普通环境及清除 PYTHONPATH/VIRTUAL_ENV、仅 Windows 系统 PATH 的环境均重复通过完整 EXE 冒烟。本机仍安装有 Python，这不是全新无 Python 设备验收；冻结 EXE 使用自身运行库。
- [Release v0.2.0-rc.1](https://github.com/yunfei00/qrft/releases/tag/v0.2.0-rc.1) 已发布。ZIP 231,244,571 字节；SHA256 `22ac81d82ed5cd211f72607b2d85ab7d9d8f9f52635e1e552dfdbd2199c713d8`。Release 包含 ZIP 和校验文件；ZIP 内 VERSION/COMMIT/完整文件校验清单和部署文档。
- 本地最终 104 项测试、Ruff 格式/静态检查通过，无跳过；一次 Starlette httpx 弃用警告，不影响结果。性能详见 PERFORMANCE.md。
- 按原十项条件软件验收 7/10；第5真实录屏、第7双Windows/SMB、第10大视频可靠性未验收。UA-006/UA-007 是后续人工操作入口。

以下为开发阶段历史记录，最后交付状态以上述记录为准。

基线：main 58acb5f，已独立核对五条 Windows CI 全部成功，90 项测试基线。工作区干净，分支 feature/qrft-final-delivery。v1 二维码字节协议保持不变。

剩余清单：GUI 非阻塞文件检查/导出、共享播放器完整控制；Web 表格与下载/设置；取消/租约围栏/扫描进度/配置文件；流式缺包与恢复、视频顺序扫描；真实并发端到端测试；四 EXE 功能冒烟及统一带校验清单的 Release；部署、维护和排障文档。

## Phase A

- GUI 后台哈希和 PNG 导出；文件信息、纠错/像素、包范围、补传、开始延迟、暂停/继续/停止和全屏切换。
- CLI 与 GUI 共用真实播放器；有界后台 PNG 队列、包号/进度/剩余时间，退出时释放线程和文件。
- 缺包选择外部 SQLite 排序/合并区间，避免展开范围；编码持有一个文件流连续读取，PNG 导出以独占创建保护已有文件。
- 真实 Qt 自动化覆盖中文文件检查、PNG 经 ZXing 回读、暂停/继续/完成、缓存容量和启动延迟退出；GUI EXE 增加真实 Qt 自动启动/退出测试。
- 本地/提交/CI 结果按实际执行更新；真实 GUI 交互和双机 SMB 不以 offscreen 测试代替。

## 后续开发与验证

- 浏览器实测：Token 连接、中文任务创建、SMB 路径登记与三片展示、缺少 START 的中文错误、网页触发恢复后 SHA256/原始 0–255 字节一致、missing.txt 实际下载。共享路径仅登记模拟值，未读取真实共享。修复恢复后概览计数刷新与中文进度表。CI 3a731a2 六项全绿（Windows Delivery 38040094866）；界面最后调整需新 CI 确认。

- Phase A 提交 aa255d3，Python CI 通过；GUI EXE 启动门禁实际发现 Qt 6.12 DLL 问题。改为锁定 PySide6 6.9.3 后本机无控制台 EXE 创建窗口并退出，exit=0。
- 缺包 API 默认返回最多 1000 个 ID，支持 after/limit 游标和 missing_count；完整下载支持鉴权 TXT/CSV/JSON 流式生成，不接受任意下载路径。
- 控制中心恢复按 SQLite 排序游标写入并校验 CRC/SHA256/MD5，不加载全部包号。断电后从持久化 SQLite 重新恢复，暂未实现跳过已写磁盘区块的恢复检查点。
- Web 增加节点概览、视频/时间片表格和下载。任务取消停止调度并拒绝 DATA 提交。Worker 可用 JSON 配置及 QRFT_API_TOKEN 环境变量，避免在命令行暴露 Token。
- 视频采样一次定位后顺序读取；新增 scripts/benchmark.py 与 scripts/windows_smoke.py。统一交付工作流执行四 EXE 的真实 PNG→AVI→解码→HTTP Worker→SQLite→文件哈希链路。
- 新 Worker 已实现 HTTP 租约代次围栏、成功批次后扫描检查点与一秒重扫重叠；旧客户端省略 lease_token 时保持兼容，不能获得代次围栏保护。重新扫描 API 会重置检查点且保留已收包。
- Web 增加中文表头、系统概览/配置说明、重复包累计、节点在线/处理中状态和取消/重新扫描操作。长期 GUI 稳定性及真实桌面观感仍未验收。
- v1 DATA 没有 file_id，CRC 只能检验包完整性，不能证明来源。绑定 START、包号/长度检查、冲突隔离和最终 SHA256/MD5 拒绝错误文件；同尺寸来源混入可能直到整体哈希时才发现，不能宣称逐包来源鉴别。
- 四 EXE 初版统一交付工作流在 00e473a 通过（run 38039314251）；后续更新加入真实并发双 Worker EXE 和 CLI 播放完成退出测试，需重新等待 CI。

## 性能实测（Windows 本机）

候选版版本 0.2.0rc1；新增本地解码磁盘包号索引及中文 PNG 路径读取，合成 AVI 回归覆盖空文件、中文文本、PDF/ZIP/EXE 扩展名二进制和全部字节值。本地最新 104 项测试通过，无跳过；发布及最终 CI 记录待实际完成后补充。部署/开发维护与排障见 OPERATIONS.md。

运行：`uv run --no-sync python scripts/benchmark.py --output temp/benchmark-1g.json`。
真实写入并读取 1,073,741,824 字节文件，哈希 2.82 秒，Python 分配峰值 2,106,646 字节。
10 万包号中实际写入 SQLite 5 万个 256 字节数据包，1.53 秒；导出 5 万缺包的三份报告 1.40 秒，Python 分配峰值 376,165 字节。
这些是本机一次运行结果，不能代表原生 RSS、完整 1GB 二维码传输、大视频、SMB 或真实多机吞吐。
