# 核心架构

```text
encoder_cli → 二维码 / 外部录屏 → decoder / worker → control → 合并恢复
                                      ↑               ↑
                                  decoder_gui      Web 界面

批量项目：single_decoder → 项目 SQLite → 缺包报告 / output
```

| 模块 | 职责 |
|---|---|
| `core` | 唯一 v2 协议、文件检查、二维码渲染、包校验及流式恢复 |
| `encoder_cli` | 唯一编码实现；命令行、内存 ZIP、二维码导出和 OpenCV 播放 |
| `decoder` | OpenCV 读取视频、ZXing 识别、分布式 Worker 和本地视频恢复 |
| `decoder_gui` | PySide6 解码桌面界面；复用 Control API，管理本地 Control/Worker 进程 |
| `control` | FastAPI、SQLite、任务与租约调度、包去重和冲突隔离、缺包和恢复、Web 界面 |
| `single_decoder` | 无服务批量项目；多视频来源记录、断点续跑、独立合并和目录内容校验 |

默认分块 2100 字节，可由编码 CLI 更改，所有消费者从 START 读取实际值。编码器不依赖 Qt。桌面解码器默认自动管理本地服务，也可连接已有调度中心；打包后子进程通过同一个 Decoder EXE 的显式子命令启动。

Worker 领取的是逻辑时间片，直接读取视频指定范围，不复制或物理切片整个视频。时间片重叠、租约续期和检查点保证重试；中心按包号合并，最终校验实际文件 MD5。未知来源视频不能自动归入同一文件。

批量项目模式为无需服务的本地用法：`videos/` 存录屏，`state/` 保存 SQLite 状态，`reports/` 存缺包和结果，`output/` 放恢复文件。`decode PROJECT` 扫描并恢复，`merge PROJECT` 只合并已收到的数据。桌面任务数据与批量项目数据库互不混用。

发布只保留三个程序：编码 CLI、解码 GUI、调度中心。验收平台、编码 GUI、独立 encoder2100、旧协议和历史阶段脚本已移除；必要回归由 tests 和统一 Windows 冒烟测试承担。
