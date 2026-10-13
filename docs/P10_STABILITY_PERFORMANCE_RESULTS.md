# QRFT v2-P10 稳定性与性能实测结果

核心门禁：**PASS**。所有速度均按实际源工作树测量；MP4 为编码核心生成的真实可解码合成视频，不是 Windows 截图工具录屏。P8/P9 用户验收结论保持，不要求重复操作。

## 基线与资源保护

源码基线 `01db02d6d9831868311c3f6afeaf418eb8fcaef1`；性能执行期间工作树有本次基准代码修改。初始全量 pytest 211 项通过，最终回归 221 项通过。OS/Python/依赖与硬件见 JSON。

所有数据保存在独占 `temp/p10-fabb1648a2ef4d4aa8babb9f750c4f1b`，具有 OWNER.txt；未清理历史录像或用户工作区。资源策略为 2 小时总预算、30 分钟单项建议上限、15 GiB 生成数据上限，空闲空间保障取 8 GiB 与初始余量 20% 的较大值。源码持续采样 RSS/CPU/进程 I/O、空闲空间并保存中断报告。

## 同视频 1 / 2 / 4 Worker 对比

每个原始 64 KiB / 1 MiB 样本生成一次，同一 MP4、相同 1 秒时间片/100 ms 重叠，各档重复三次并轮换顺序。扫描时间包含 Worker 启动及调度，复用了 OS 文件缓存；不推算跨机 SMB 速度。

| 文件 | Worker | 次数 | 中位扫描秒 | 最小–最大秒 | 包/秒中位 | 加速比 | RSS 采样峰值 MiB | CPU 合计峰值 % |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| 64 KiB | 1 | 3 | 5.031 | 4.813–5.032 | 9.342 | 1.000 | 166.24 | 146.8 |
| 64 KiB | 2 | 3 | 3.031 | 2.891–3.047 | 15.506 | 1.660 | 267.98 | 247.6 |
| 64 KiB | 4 | 3 | 2.110 | 2.093–2.172 | 22.275 | 2.384 | 465.07 | 510.3 |
| 1024 KiB | 1 | 3 | 50.844 | 49.172–51.188 | 14.731 | 1.000 | 172.14 | 182.0 |
| 1024 KiB | 2 | 3 | 26.579 | 24.328–26.656 | 28.180 | 1.913 | 270.40 | 312.5 |
| 1024 KiB | 4 | 3 | 16.250 | 15.875–17.797 | 46.092 | 3.129 | 472.35 | 487.5 |

## 额外规模及素材生成

- 1 MiB：789 帧、20 FPS、926×926、视频 39.450 秒；生成 48.875 秒（4 个有界渲染进程），2 Worker 扫描 25.500 秒、恢复 0.078 秒，749 个有效包、缺包/冲突 0，逐字节及 MD5/SHA256 一致。实际暂停/恢复：False。
- 10 MiB：7530 帧、20 FPS、926×926、视频 376.500 秒；生成 592.437 秒（4 个有界渲染进程），2 Worker 扫描 265.375 秒、恢复 0.563 秒，7490 个有效包、缺包/冲突 0，逐字节及 MD5/SHA256 一致。实际暂停/恢复：True。
- 4 MiB：3036 帧、20 FPS、926×926、视频 151.800 秒；生成 480.531 秒（1 个有界渲染进程），2 Worker 扫描 96.781 秒、恢复 0.219 秒，2996 个有效包、缺包/冲突 0，逐字节及 MD5/SHA256 一致。实际暂停/恢复：True。

有界渲染仅用于验收 MP4 的素材生成器，队列最多 2×进程数；普通编码 GUI/播放器、v2 协议及口令行为未修改。1 MiB 顺序/并行比较使用相同源文件和二维码/视频参数；实测数值与 video_sha256 可在 JSON 核对，这是单次生成策略比较，不是传输提速保证。

## 真实 SQLite 存储恢复（不是 QR 视频）

| 文件 MiB | 包数 | 入库秒 | 恢复秒 | RSS 峰值 MiB | DB MiB |
|---:|---:|---:|---:|---:|---:|
| 100 | 74899 | 5.985 | 2.922 | 54.40 | 294.28 |
| 1024 | 766959 | 71.781 | 32.953 | 55.32 | 3014.38 |

这些测试真实调用 v2 逐包 MD5、SQLite ingest、流式缺包导出及 recovery；奇偶包乱序入库、删除/补回缺包、重复幂等、冲突隔离、数据库关闭重开、已有文件不覆盖均验证。不可写路径用独占目录内的同名普通文件占位测试，没有改动用户 ACL。v2 不要求 FINISH 才能恢复，完整包和最终 MD5 仍是必要条件。查询计时与主键索引 EXPLAIN 证据见 JSON；进程 I/O 是逻辑计数，包含缓存/IPC及全部测试操作，不是物理磁盘带宽。

## 原生 GUI 长期稳定性与故障恢复

- 原生 `windows` GUI：实际 1800.109 秒，重复完成 61 次短 MP4 扫描；RSS 起始/峰值/结束 355.14/392.25/176.09 MiB，CPU 平均/峰值 199.4/362.4%，后台 GUI 错误 0，中途 GUI/Control 关闭重开及最终进程清理通过。
- 原生 `windows` GUI：实际 600.016 秒，重复完成 21 次短 MP4 扫描；RSS 起始/峰值/结束 336.48/387.25/176.30 MiB，CPU 平均/峰值 195.3/344.8%，后台 GUI 错误 0，中途 GUI/Control 关闭重开及最终进程清理通过。
- HTTP 503, renewal, actual Worker kill, checkpoint takeover, stale fencing：PASS。
- abrupt Control crash / new authenticated Control / persisted packets and checkpoints：PASS。
- Pause/Resume and Cancel/Resume keep verified packets：PASS。
- real truncated MP4 rejected：PASS。

以上长时测试为 GUI + 重复短视频持续负载，不冒充单段长视频；每分钟截图、资源样本、心跳/时间片、数据库及日志完整留存于证据目录。进程故障使用真实 OS 终止和 HTTP 503，租约按实际时间过期、检查点接管及旧租约围栏有原始证据。

## 未测范围与 P11 建议

- 50/100 MiB full QR video：**NOT RUN** — conditional video exceeds per-item time/evidence budget; real SQLite stresses separately measured。
- 1 GiB full QR video：**NOT TESTED** — prohibited by P10 plan; 1 GiB storage/recovery is a separate test。
- 60-minute native GUI endurance：**NOT RUN** — does not fit remaining two-hour controlled workload budget。
- physical dual Windows/SMB and physical network disconnect：**NOT TESTED** — requires second physical host。
- new real screen-capture throughput or single long-video performance：**NOT TESTED** — synthetic videos and repeated short scans do not establish these measurements; existing P8/P9 user PASS retained。

## 本轮修复与证据闭环

原生冒烟暴露了自动刷新忙碌时新建任务点击被直接忽略的问题。先添加真实 Control/Qt 对话框回归并确认失败，再将 new_task 的 busy 拒绝改为仅拒绝关闭阶段；业务请求继续走既有串行队列，回归与原生长时运行确认修复。运行器的 ASCII 测试输入改用真实 Qt 按键并回读校验，防止未到达控件的剪贴板操作导致参数误报。失败尝试目录保留，未删除测试。

Windows Python 3.12 的 GetTickCount64 单调时钟分辨率约 15.6 ms，原始短查询可能记录为零。查询计时改用 perf_counter（QueryPerformanceCounter），并对原包库只读复测；未将计时修正说成数据库性能优化。编码端 GUI/CLI、1400 字节、帧格式/MD5/START/FINISH 与 v1 兼容未改；解码 GUI 仅包含上述点击修复。


P10 实测允许进入 P11 候选版准备，但不支持直接宣称全部硬件/超大视频生产验收完成。P11 应验证打包后启动、相同源码回归和实际 EXE 冒烟、版本/校验清单及手册；分布式 SMB 功能仍须按现有 UA-006/解码手册在第二台物理 Windows 验收。当前 PR 保持 Draft，本轮没有合并、Tag、EXE 构建或 Release。

原始各次数据、哈希、CPU/RSS/I/O、节点/时间片证明及资源策略见 [P10_BENCHMARK_SUMMARY.json](P10_BENCHMARK_SUMMARY.json)。代码提交 `c266015b0bbc426e2e049018ab9d1b331fe424c1` 已推送；[Windows Python CI 38349131223](https://github.com/yunfei00/qrft/actions/runs/38349131223) 成功（3 分 33 秒），格式/静态/全量测试、原生源码 GUI 启动/安全退出及二维码/ZXing/AVI/API/SQLite 分项全部通过。PR #7 保持 Open / Draft，没有合并、Tag、EXE 构建或 Release。

## 开发者复现入口（本轮用户不需重做）

只在可交互 Windows 桌面运行。每次使用新 UUID；非零退出须读取保存的 failure/blocked/cancelled 报告，不能把未完成项写 PASS。1 GiB 完整 QR 视频禁止生成。以下命令在同一个 PowerShell 会话依次执行：

```powershell
$repo = 'D:\code_2026\qrft'
Set-Location $repo
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '依赖同步失败' }
$p10Root = Join-Path $repo ('temp\p10-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $p10Root | Out-Null
'QRFT P10 isolated acceptance; retain evidence; created by current task' | Set-Content -LiteralPath (Join-Path $p10Root 'OWNER.txt') -Encoding utf8
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync pytest -q --basetemp (Join-Path $p10Root 'baseline-pytest') | Tee-Object -FilePath (Join-Path $p10Root 'baseline-pytest.log')
uv run --no-sync python -u scripts/p10_acceptance.py matrix --root $p10Root
uv run --no-sync python -u scripts/p10_acceptance.py matrix --root $p10Root --sizes-kib 1024 --workers 2 --repeats 1 --render-processes 4
uv run --no-sync python -u scripts/p10_acceptance.py matrix --root $p10Root --sizes-kib 10240 --workers 2 --repeats 1 --render-processes 4
uv run --no-sync python -u scripts/p10_acceptance.py storage --root $p10Root --file-mib 100
uv run --no-sync python -u scripts/p10_acceptance.py storage --root $p10Root --file-mib 1024
$fixture = Join-Path $p10Root 'matrix\fixture-1024kib\fixture.json'
uv run --no-sync python -u scripts/p10_acceptance.py faults --root $p10Root --fixture $fixture
uv run --no-sync python -u scripts/p10_acceptance.py stability --root $p10Root --fixture $fixture --seconds 600
uv run --no-sync python -u scripts/p10_acceptance.py stability --root $p10Root --fixture $fixture --seconds 1800
uv run --no-sync pytest -q --basetemp (Join-Path $p10Root 'final-pytest') | Tee-Object -FilePath (Join-Path $p10Root 'final-pytest.log')
uv run --no-sync python scripts/p10_report.py --root $p10Root --output (Join-Path $p10Root 'published-report')
```

报告生成器可输出到 docs；上例使用独占目录，避免覆盖仓库既有证据。60 分钟仅在剩余总预算足够时独立运行，否则运行器会阻止启动。Ctrl+C 可中断并保存取消结果；只关闭自有进程，不自动删除证据目录。
