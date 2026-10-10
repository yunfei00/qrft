# QRFT Windows 部署、维护与排障

## 部署候选版本

从仓库 Releases 下载 Windows 完整压缩包，检查 Release 附带的 ZIP SHA256，再解压到独立目录。保留四个程序目录及各自 `_internal` 子目录；不要只复制 EXE。目标机无需 Python。候选版尚未完成真实双机 SMB、长视频及人工 GUI 验收，使用测试文件执行 UA-006 后再用于实际传输。

控制机启动前在 PowerShell 设置配置（Token 不写入公开配置文件）：

```powershell
$env:QRFT_API_TOKEN = Read-Host 'API Token'
$env:QRFT_DB_PATH = 'C:\QRFT-data\control.sqlite3'
$env:QRFT_OUTPUT_DIR = 'C:\QRFT-data\recovered'
& .\QRFT-Control\QRFT-Control.exe --host 127.0.0.1 --port 8787
```

浏览器打开 http://127.0.0.1:8787/，输入同一 Token；新建任务、登记节点可访问的视频路径及真实时长、查看任务与节点状态。需要局域网节点时改用明确的局域网监听地址并允许对应防火墙端口；API Token 保持开启。HTTP 不加密，跨不可信网络部署需在前端配置 HTTPS 反向代理。

每个任务只对应一个原始文件。同一文件的录屏、补传录屏可登记为多个视频。SMB 使用只读共享，例如 `\\SERVER\qrft-video\recording.avi`，确保运行 Worker 的 Windows 账户有读取权限；浏览器登记路径不会读取视频，实际访问由 Worker 执行。

节点配置 `worker.json`：

```json
{"server":"http://CONTROL:8787","node_id":"node-a"}
```

```powershell
$env:QRFT_API_TOKEN = Read-Host 'API Token'
& .\QRFT-Decoder\QRFT-Decoder.exe worker --config .\worker.json
```

每台节点使用不同 node_id。Ctrl+C 退出节点；已确认的包留在 SQLite，未完成租约 120 秒后可重新领取。每 30 秒心跳/续租，成功批次后周期保存扫描位置，重领时重扫一秒。兼容旧 HTTP 客户端，但代次围栏与检查点需要新 Worker。无法打开视频时日志显示路径，时间片不标为完成，租约到期后重试；先修复共享权限或视频路径。

## 编码与恢复

启动 GUI，选择任意文件，后台检查文件信息/哈希；设置分块、纠错、播放间隔和开始延迟。通常从 256 字节、M 纠错开始；二维码容量不足时减少分块。设置包范围或导入 missing.txt 可选择补传。播放窗口支持空格暂停、F11 全屏、Esc 退出全屏/停止；主窗口可以停止。PNG 导出到新的空目录，已有同名文件会拒绝覆盖。

```powershell
& .\QRFT-Encoder-CLI\QRFT-Encoder-CLI.exe play 'C:\测试\文件.zip' --chunk-size 256 --interval-ms 300
& .\QRFT-Encoder-CLI\QRFT-Encoder-CLI.exe export 'C:\测试\文件.zip' --output 'C:\测试\新PNG目录' --chunk-size 256
& .\QRFT-Encoder-CLI\QRFT-Encoder-CLI.exe play 'C:\测试\文件.zip' --retransmit 'C:\测试\missing.txt'
& .\QRFT-Decoder\QRFT-Decoder.exe 'C:\测试\录屏.avi' --output 'C:\测试\本地恢复'
```

先用外部录屏软件完整记录 START、DATA、FINISH；自动化合成 AVI 不代表真实屏幕录制质量。控制界面提供缺包 TXT/CSV/JSON 下载，TXT 可直接补传；把补传视频登记到同一任务后继续运行 Worker。文件恢复只有 CRC 和整体 SHA256/MD5 通过且已见 FINISH 才发布到任务目录 `files`，不覆盖已有最终文件。缺失 START/FINISH 时请重新录制相应会话帧，不能用假元数据绕过校验。

## 维护和故障排查

- 401：确认浏览器、控制端和 Worker 使用相同 Token；503：控制端缺少 QRFT_API_TOKEN。不要把 Token 附在日志或 URL 中。
- 409 lease_invalid：租约过期、取消或重新扫描使代次失效；保留已收包，等待新领取。不同电脑不能共用 node_id。
- 409 conflicting START：登记了不同来源文件；建立新任务，避免向原任务混入数据。v1 DATA 没有来源标识，同尺寸混入可能直到最终哈希才发现。
- 哈希失败：检查冲突统计与原文件是否改变。保留数据库和报告，通过重新扫描/正确补传排查，不自动删除冲突或覆盖用户文件。
- 时间片 done 不代表全部包已收到；查看 missing_count 和 FINISH 状态。模糊、采样频率不足、二维码过小会造成缺包；降低播放速度、改善录屏、重新扫描或补传。
- GUI 启动失败：完整解压运行库；本版锁定 PySide6 6.9.3，CI 对实际 EXE 启动测试。保留异常提示、Windows 版本、Release 版本，禁止用旧版本 `_internal` 混搭。
- 恢复空间不足：确认磁盘空间足够容纳 SQLite 原始包、临时文件、最终文件和缺包报告。恢复中断后可从持久化数据库重做恢复；当前不会跳过上次已写临时区块。

备份前先退出 Worker 和控制中心，再一起复制数据库、可能存在的 `-wal`/`-shm` 及输出目录；不要在运行中仅复制主 SQLite 文件。升级在新目录解压并保留原版与备份，首次启动执行添加列/索引的兼容迁移。回滚前恢复对应版本备份，不能把未知数据库文件直接覆盖。

## 开发者维护

```powershell
uv sync --locked --python 3.12 --all-extras --group dev
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync pytest -q
uv run --no-sync python scripts/benchmark.py --output temp/benchmark.json
uv run --no-sync python scripts/windows_smoke.py --dist dist
```

Windows Delivery 工作流同一提交构建四个 EXE，实际运行 GUI、CLI 播放/PNG 导出、AVI 本地恢复、两个并发 Worker EXE、HTTP 控制中心和最终 SHA256 校验，再汇总文档与所有运行库校验清单。测试规模、时间和内存口径见 FINAL_DELIVERY.md；性能脚本 Python 分配峰值不等于总进程 RSS。发布前核对 main 的六项 CI 全绿和 COMMIT.txt，创建候选版 Release，校验 ZIP 和全部运行库，不绕过失败门禁。
