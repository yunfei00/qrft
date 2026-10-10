# 分布式解码自动化验证

本地使用 Windows、uv 管理 Python 3.12、完整 optional dependencies。模拟 HTTP 使用 FastAPI TestClient，视频测试生成真实 MJPG AVI 后由 OpenCV/ZXing 识别。它们不是双机 SMB 或实际屏幕录制验收。

| 要求 | 自动化证据 |
|---|---|
| 单 Worker 完整视频 | test_distributed_recovery::test_workers_real_avi[1] |
| 两 Worker 不同时间片 | test_workers_real_avi[2]，模拟两个节点，真实 AVI |
| 节点乱序提交 / 当前片无 START | 后片先扫描；test_data_before_start_retransmission_and_restart |
| 重复包幂等 / 同 ID 冲突隔离 | test_control_packets、test_data_before_start_retransmission_and_restart |
| 中途退出 / 租约到期重领 | test_worker::test_interrupted_scan_never_completes、test_scheduler::test_claim_lease_and_completion |
| 无可识别帧期间续租 / 续租失败 | test_worker::test_renew_without_recognized_frames_and_finish、test_renew_failure_never_completes |
| HTTP 故障与退避 / 认证错误不重试 | test_worker::test_retry_network_and_no_retry_auth_or_claim |
| 部分二维码不可识别 / 重扫补传 | test_unreadable_qr_in_real_video_and_retransmission，真实 AVI 白帧移除 DATA 1 |
| 完整重组、SHA256/MD5、错误哈希不发布 | test_reassemble、test_hash_failure_does_not_publish |
| 空文件 / 全部字节 / 无扩展名 / 报告与临时文件同名 | test_data_before_start_retransmission_and_restart 参数化 |
| Windows/UNC 路径 | test_control_api、test_worker（路径模拟，不代表 SMB I/O 验收） |
| FINISH 持久化及批次事务 | test_finish_batch_rollback_and_manifest_conflict |
| API Token / Web 登录壳 | test_health_and_token_required、test_new_operations_require_token；Web JavaScript 通过 node --check |

运行：

```powershell
uv sync --locked --python 3.12 --all-extras --group dev
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync pytest -q
```

本机旧系统临时目录 ACL 异常时设置 `$env:PYTEST_DEBUG_TEMPROOT = "$PWD/temp"`；不改用户已有临时目录权限。真实双设备验收见 USER_ACTIONS.md UA-006。

已知限制：v1 DATA/FINISH 没有会话 ID，不能由单包鉴别所有文件来源；按任务管理录屏、START 一致性、冲突隔离及最终哈希共同防止错误文件发布。数据库持久化允许中断后重新重建，尚不复用临时文件写入进度。包号/缺包集合使用与包数相关的内存，尚无大视频性能证据。
