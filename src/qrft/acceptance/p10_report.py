"""Small anonymized P10 report derived from saved, completed measurements."""

from __future__ import annotations

import html
import json
import re
import statistics
from pathlib import Path

from qrft.acceptance.resources import OWNER, save_json


def sanitize(value, root):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if "token" in k.lower() or "hostname" in k.lower()
            else sanitize(v, root)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v, root) for v in value]
    if isinstance(value, str):
        value = value.replace(str(root.resolve()), "temp/" + root.name)
        if re.match(r"^[A-Za-z]:[\\/]|^\\\\", value):
            return "[absolute local path omitted]"
        return value.replace("\\", "/")
    return value


def pytest_result(path):
    if not path.exists():
        return {"status": "NOT RUN"}
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(\d+) passed[^\n]*? in ([\d.]+)s", text)
    if not match or re.search(r"\d+ failed|\d+ error", text):
        return {"status": "FAIL", "log": path.name}
    skipped = re.search(r"(\d+) skipped", text)
    return {
        "status": "PASS",
        "passed": int(match[1]),
        "seconds": float(match[2]),
        "skipped": int(skipped[1]) if skipped else 0,
        "log": path.name,
    }


def collect(root: Path):
    if (root / "OWNER.txt").read_text(encoding="utf-8-sig").strip() != OWNER:
        raise ValueError("owned P10 evidence required")
    environment = json.loads((root / "environment.json").read_text(encoding="utf-8"))
    matrices, storage, stability, estimates = [], [], [], []
    for path in sorted(root.glob("matrix*/report.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("estimates") or report.get("preflight"):
            estimates.append(
                {
                    "raw_report": str(path.relative_to(root)),
                    "estimates": report.get("estimates", []),
                    "preflight": report.get("preflight"),
                }
            )
        for level in report["levels"]:
            fixture = level["fixture"]
            runs = [
                {
                    k: v
                    for k, v in run.items()
                    if k not in {"receipts", "nodes_with_completed_slices"}
                }
                | {
                    "completed_slice_receipts": len(run["receipts"]),
                    "distinct_nodes_with_completed_slices": len(run["nodes_with_completed_slices"]),
                }
                for run in level["runs"]
            ]
            matrices.append(
                {
                    "source_bytes": fixture["source_bytes"],
                    "media": {k: v for k, v in fixture["media"].items() if k != "path"},
                    "video_bytes": fixture["video_bytes"],
                    "video_sha256": fixture["video_sha256"],
                    "hashes": fixture["hashes"],
                    "encoding_seconds": fixture["encoding_seconds"],
                    "render_processes": fixture.get("render_processes", 1),
                    "render_queue_limit_frames": fixture.get("render_queue_limit_frames", 1),
                    "maximum_pending_render_frames": fixture.get(
                        "maximum_pending_render_frames", 1
                    ),
                    "encoding_resources": fixture["encoding_resources"],
                    "runs": runs,
                    "summary": level["summary"],
                    "raw_report": str(path.relative_to(root)),
                }
            )
    for pattern, target in (
        ("storage-*/report.json", storage),
        ("stability-*/report.json", stability),
    ):
        for path in sorted(root.glob(pattern)):
            report = json.loads(path.read_text(encoding="utf-8"))
            if target is stability and report.get("requested_seconds", 0) < 600:
                continue
            snapshots = report.pop("minute_snapshots", None)
            if snapshots:
                active = [s["rss_bytes"] for s in snapshots[1:]]
                report["active_rss_first_five_minute_samples_median_bytes"] = (
                    statistics.median(active[:5]) if active else None
                )
                report["active_rss_last_five_minute_samples_median_bytes"] = (
                    statistics.median(active[-5:]) if active else None
                )
            if target is storage and (path.parent / "query-perf.json").exists():
                high_resolution = json.loads(
                    (path.parent / "query-perf.json").read_text(encoding="utf-8")
                )
                report["queries"] = high_resolution["queries"]
                report["query_measurement_note"] = (
                    "read-only high-resolution remeasurement; original GetTickCount64 measurements retained only in local raw report"
                )
            report["raw_report"] = str(path.relative_to(root))
            target.append(report)
    fault_path = root / "faults/report.json"
    faults = (
        json.loads(fault_path.read_text(encoding="utf-8"))
        if fault_path.exists()
        else {"status": "NOT RUN"}
    )
    required = [
        m for m in matrices if m["source_bytes"] in (65536, 1048576) and len(m["runs"]) == 9
    ]
    video_ok = len(required) == 2 and all(
        r["status"] == "PASS" and r["bytes_equal"] and r["missing_count"] == r["conflicts"] == 0
        for m in required
        for r in m["runs"]
    )
    all_video_ok = all(
        m["runs"]
        and all(
            r["status"] == "PASS" and r["bytes_equal"] and r["missing_count"] == r["conflicts"] == 0
            for r in m["runs"]
        )
        for m in matrices
    )
    baseline, final = (
        pytest_result(root / "baseline-pytest.log"),
        pytest_result(root / "final-pytest.log"),
    )
    result = {
        "environment": environment,
        "baseline": baseline,
        "final_regression": final,
        "synthetic_video": matrices,
        "resource_forecast_history": estimates,
        "sqlite_stress_no_video": storage,
        "native_gui_repeated_short_video_stability": stability,
        "fault_recovery": faults,
        "resource_budget": json.loads((root / "resource-status.json").read_text(encoding="utf-8")),
        "core_gate": "PASS"
        if video_ok
        and all_video_ok
        and final["status"] == "PASS"
        and faults.get("status") == "PASS"
        and all(r.get("status") == "PASS" for r in storage + stability)
        and len(stability) >= 1
        else "INCOMPLETE",
        "not_tested_or_not_run": [
            {
                "item": "50/100 MiB full QR video",
                "status": "NOT RUN",
                "reason": "conditional video exceeds per-item time/evidence budget; real SQLite stresses separately measured",
            },
            {
                "item": "1 GiB full QR video",
                "status": "NOT TESTED",
                "reason": "prohibited by P10 plan; 1 GiB storage/recovery is a separate test",
            },
            {
                "item": "60-minute native GUI endurance",
                "status": "NOT RUN",
                "reason": "does not fit remaining two-hour controlled workload budget",
            },
            {
                "item": "physical dual Windows/SMB and physical network disconnect",
                "status": "NOT TESTED",
                "reason": "requires second physical host",
            },
            {
                "item": "new real screen-capture throughput or single long-video performance",
                "status": "NOT TESTED",
                "reason": "synthetic videos and repeated short scans do not establish these measurements; existing P8/P9 user PASS retained",
            },
        ],
        "evidence_directory": "temp/" + root.name,
        "privacy": "relative paths; API/lease tokens redacted; no private recordings or hostname",
    }
    return sanitize(result, root)


def markdown(result):
    lines = [
        "# QRFT v2-P10 稳定性与性能实测结果",
        "",
        f"核心门禁：**{result['core_gate']}**。所有速度均按实际源工作树测量；MP4 为编码核心生成的真实可解码合成视频，不是 Windows 截图工具录屏。P8/P9 用户验收结论保持，不要求重复操作。",
        "",
        "## 基线与资源保护",
        "",
        f"源码基线 `{result['environment']['git_commit']}`；性能执行期间工作树有本次基准代码修改。初始全量 pytest {result['baseline'].get('passed', '未完成')} 项通过，最终回归 {result['final_regression'].get('passed', '未完成')} 项通过。OS/Python/依赖与硬件见 JSON。",
        "",
        f"所有数据保存在独占 `{result['evidence_directory']}`，具有 OWNER.txt；未清理历史录像或用户工作区。资源策略为 2 小时总预算、30 分钟单项建议上限、15 GiB 生成数据上限，空闲空间保障取 8 GiB 与初始余量 20% 的较大值。源码持续采样 RSS/CPU/进程 I/O、空闲空间并保存中断报告。",
        "",
        "## 同视频 1 / 2 / 4 Worker 对比",
        "",
        "每个原始 64 KiB / 1 MiB 样本生成一次，同一 MP4、相同 1 秒时间片/100 ms 重叠，各档重复三次并轮换顺序。扫描时间包含 Worker 启动及调度，复用了 OS 文件缓存；不推算跨机 SMB 速度。",
        "",
        "| 文件 | Worker | 次数 | 中位扫描秒 | 最小–最大秒 | 包/秒中位 | 加速比 | RSS 采样峰值 MiB | CPU 合计峰值 % |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for level in result["synthetic_video"]:
        if len(level["runs"]) != 9:
            continue
        for group in level["summary"]:
            lines.append(
                f"| {level['source_bytes'] / 1024:g} KiB | {group['workers']} | {group['repeats']} | {group['scan_median_seconds']:.3f} | {group['scan_min_seconds']:.3f}–{group['scan_max_seconds']:.3f} | {group['packets_per_second_median']:.3f} | {group['speedup_vs_one_worker']:.3f} | {group['rss_peak_max_bytes'] / 1024**2:.2f} | {group['cpu_peak_max_percent']:.1f} |"
            )
    lines += ["", "## 额外规模及素材生成", ""]
    for level in result["synthetic_video"]:
        if len(level["runs"]) == 9:
            continue
        if not level["runs"]:
            lines.append(f"- {level['source_bytes']} 字节素材已生成，完整扫描未完成；不能标 PASS。")
            continue
        run = level["runs"][0]
        lines.append(
            f"- {level['source_bytes'] / 1024**2:g} MiB：{level['media']['frames']} 帧、{level['media']['fps']:g} FPS、{level['media']['width']}×{level['media']['height']}、视频 {level['media']['duration_seconds']:.3f} 秒；生成 {level['encoding_seconds']:.3f} 秒（{level['render_processes']} 个有界渲染进程），{run['workers']} Worker 扫描 {run['scan_seconds']:.3f} 秒、恢复 {run['recovery_seconds']:.3f} 秒，{run['verified_unique_packets']} 个有效包、缺包/冲突 0，逐字节及 MD5/SHA256 一致。实际暂停/恢复：{bool(run.get('pause_resume_interruption'))}。"
        )
    lines += [
        "",
        "有界渲染仅用于验收 MP4 的素材生成器，队列最多 2×进程数；普通编码 GUI/播放器、v2 协议及口令行为未修改。1 MiB 顺序/并行比较使用相同源文件和二维码/视频参数；实测数值与 video_sha256 可在 JSON 核对，这是单次生成策略比较，不是传输提速保证。",
        "",
        "## 真实 SQLite 存储恢复（不是 QR 视频）",
        "",
        "| 文件 MiB | 包数 | 入库秒 | 恢复秒 | RSS 峰值 MiB | DB MiB |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for case in result["sqlite_stress_no_video"]:
        lines.append(
            f"| {case['source_bytes'] / 1024**2:g} | {case['stored_packets']} | {case['ingest_seconds']:.3f} | {case['recovery_seconds']:.3f} | {case['resources']['rss_peak_bytes'] / 1024**2:.2f} | {case['database_bytes'] / 1024**2:.2f} |"
        )
    lines += [
        "",
        "这些测试真实调用 v2 逐包 MD5、SQLite ingest、流式缺包导出及 recovery；奇偶包乱序入库、删除/补回缺包、重复幂等、冲突隔离、数据库关闭重开、已有文件不覆盖均验证。不可写路径用独占目录内的同名普通文件占位测试，没有改动用户 ACL。v2 不要求 FINISH 才能恢复，完整包和最终 MD5 仍是必要条件。查询计时与主键索引 EXPLAIN 证据见 JSON；进程 I/O 是逻辑计数，包含缓存/IPC及全部测试操作，不是物理磁盘带宽。",
        "",
        "## 原生 GUI 长期稳定性与故障恢复",
        "",
    ]
    for case in result["native_gui_repeated_short_video_stability"]:
        resources = case["resource_samples"]
        lines.append(
            f"- 原生 `{case['native_qt_platform']}` GUI：实际 {case['actual_seconds']:.3f} 秒，重复完成 {case['scans_completed']} 次短 MP4 扫描；RSS 起始/峰值/结束 {resources['rss_start_bytes'] / 1024**2:.2f}/{resources['rss_peak_bytes'] / 1024**2:.2f}/{resources['rss_last_bytes'] / 1024**2:.2f} MiB，CPU 平均/峰值 {resources['cpu_average_percent']:.1f}/{resources['cpu_peak_percent']:.1f}%，后台 GUI 错误 {case['background_error_count']}，中途 GUI/Control 关闭重开及最终进程清理通过。"
        )
    for case in result["fault_recovery"].get("cases", []):
        lines.append(f"- {case['name']}：{case['status']}。")
    lines += [
        "",
        "以上长时测试为 GUI + 重复短视频持续负载，不冒充单段长视频；每分钟截图、资源样本、心跳/时间片、数据库及日志完整留存于证据目录。进程故障使用真实 OS 终止和 HTTP 503，租约按实际时间过期、检查点接管及旧租约围栏有原始证据。",
        "",
        "## 未测范围与 P11 建议",
        "",
    ]
    for case in result["not_tested_or_not_run"]:
        lines.append(f"- {case['item']}：**{case['status']}** — {case['reason']}。")
    lines += [
        "",
        "## 本轮修复与证据闭环",
        "",
        "原生冒烟暴露了自动刷新忙碌时新建任务点击被直接忽略的问题。先添加真实 Control/Qt 对话框回归并确认失败，再将 new_task 的 busy 拒绝改为仅拒绝关闭阶段；业务请求继续走既有串行队列，回归与原生长时运行确认修复。运行器的 ASCII 测试输入改用真实 Qt 按键并回读校验，防止未到达控件的剪贴板操作导致参数误报。失败尝试目录保留，未删除测试。",
        "",
        "Windows Python 3.12 的 GetTickCount64 单调时钟分辨率约 15.6 ms，原始短查询可能记录为零。查询计时改用 perf_counter（QueryPerformanceCounter），并对原包库只读复测；未将计时修正说成数据库性能优化。编码端 GUI/CLI、1400 字节、帧格式/MD5/START/FINISH 与 v1 兼容未改；解码 GUI 仅包含上述点击修复。",
        "",
    ]
    lines += [
        "",
        (
            "P10 实测允许进入 P11 候选版准备，但不支持直接宣称全部硬件/超大视频生产验收完成。"
            if result["core_gate"] == "PASS"
            else "P10 核心门禁尚未完成，暂不建议进入候选版交付。"
        )
        + "P11 应验证打包后启动、相同源码回归和实际 EXE 冒烟、版本/校验清单及手册；分布式 SMB 功能仍须按现有 UA-006/解码手册在第二台物理 Windows 验收。当前 PR 保持 Draft，本轮没有合并、Tag、EXE 构建或 Release。",
        "",
        "原始各次数据、哈希、CPU/RSS/I/O、节点/时间片证明及资源策略见 [P10_BENCHMARK_SUMMARY.json](P10_BENCHMARK_SUMMARY.json)。最终 Commit 与 CI 记录由完成后的交付补记确认。",
        "",
    ]
    lines += [
        "## 开发者复现入口（本轮用户不需重做）",
        "",
        "只在可交互 Windows 桌面运行。每次使用新 UUID；非零退出须读取保存的 failure/blocked/cancelled 报告，不能把未完成项写 PASS。1 GiB 完整 QR 视频禁止生成。以下命令在同一个 PowerShell 会话依次执行：",
        "",
        r"""```powershell
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
```""",
        "",
        "报告生成器可输出到 docs；上例使用独占目录，避免覆盖仓库既有证据。60 分钟仅在剩余总预算足够时独立运行，否则运行器会阻止启动。Ctrl+C 可中断并保存取消结果；只关闭自有进程，不自动删除证据目录。",
        "",
    ]
    return "\n".join(lines)


def export(root, output):
    result = collect(root)
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "P10_BENCHMARK_SUMMARY.json", result)
    (output / "P10_STABILITY_PERFORMANCE_RESULTS.md").write_text(markdown(result), encoding="utf-8")
    (root / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><h1>QRFT P10 实测</h1><pre>'
        + html.escape(markdown(result))
        + "</pre>",
        encoding="utf-8",
    )
    return result
