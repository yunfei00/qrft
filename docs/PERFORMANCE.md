# 性能测试报告（2026-10-10）

本机：Windows 11 10.0.26200，Intel i5-1135G7，16GB 内存，Python 3.12.13/uv，测试文件位于 D 盘。以下为一次实际运行结果，不是多轮统计，也不是设备性能保证。

```powershell
uv sync --locked --python 3.12 --all-extras --group dev
uv run --no-sync python scripts/benchmark.py --file-mib 1024 --packets 100000 --output temp/benchmark-1g.json
```

脚本真实顺序写入 1GiB 文件，再调用核心 inspect_file 计算 SHA256/MD5；写入 50,000 个实际 QRFT DATA 帧到 SQLite，并从 100,000 个包号中流式导出 50,000 个缺包的 TXT/CSV/JSON。使用独立临时目录，正常结束关闭 SQLite 并清理自己创建的测试目录。结果 JSON 单独保留。

| 项目 | 实测 |
|---|---|
| 文件大小 | 1,073,741,824 字节 |
| 文件 SHA256 | 2c06ade942ee3f17a048dd1064b2fab046a4bb95386d8bb41b68dc6711ac2af3 |
| 文件哈希耗时 | 2.816 秒 |
| 文件哈希 Python 分配峰值 | 2,106,646 字节 |
| SQLite 写入 50,000 包 | 1.529 秒 |
| 三格式导出 50,000 缺包 | 1.397 秒 |
| 缺包导出 Python 分配峰值 | 376,165 字节 |

SQLite 写入按事务分批，查询使用 task_id/packet_id 主键；缺包生成和控制端恢复用有序游标，有界 Python 内存。本地解码器的包号索引也改用磁盘 SQLite，缓存上限 2MiB；GUI 使用有界队列和有界预生成任务；视频在片段起点定位一次，再顺序采样。

**tracemalloc 只统计 Python 分配，不含 Qt/OpenCV/ZXing/SQLite 的原生 RSS。** 自动化测试另覆盖接近协议上限的惰性缺包迭代、真实小规模 AVI 和两个并发 Worker EXE；这些不代表大视频吞吐。

尚未测量：完整 1GB 二维码/视频链路、大视频随机定位与 ZXing 吞吐、长时间 GUI 播放、原生 RSS、恢复的大规模磁盘 I/O、真实多设备和 SMB 吞吐。默认 256 字节/包、300ms 播放约需 419 万 DATA 帧，完整 1GiB 传输播放时间约 14.6 天；本轮不伪装成完整 1GB 视频验收。当前本机 D 盘可用约 40GB，也不适合生成这种规模的完整录屏。真实规模与设备验收按 USER_ACTIONS.md UA-006/UA-007 记录，不能以缩小模拟替代。
