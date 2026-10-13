"""可追溯中文报告；未执行项目永不计为通过。"""

import csv
import html
import json
from pathlib import Path

LABELS = {
    "pending": "未开始",
    "running": "运行中",
    "passed": "通过",
    "failed": "失败",
    "skipped": "跳过",
    "blocked": "不具备条件",
}
ITEMS = {
    "environment": "环境检查",
    "encoder": "编码器测试",
    "decoder": "解码器测试",
    "control": "控制中心测试",
    "single": "单机完整链路",
    "dual": "双 Worker 并发",
    "smb": "真实双机 SMB",
    "fault": "网络故障与恢复",
    "missing": "缺包补传",
    "v2": "v2 HEX + MD5 完整链路",
    "performance": "大文件哈希性能",
    "qr_performance": "合成 AVI 解码性能",
    "stability": "GUI 长时间稳定性",
}

METRICS = {
    "scope": "测量范围",
    "resource_scope": "资源采样范围",
    "file_bytes": "文件大小（字节）",
    "hash_seconds": "SHA256 哈希耗时（秒）",
    "hash_bytes_per_second": "哈希速度（字节/秒，非传输速度）",
    "sampled_peak_rss_bytes": "进程采样内存峰值（字节）",
    "cpu_seconds": "CPU 时间（秒）",
    "cpu_percent_one_core": "CPU 使用率（单核百分比）",
    "disk_read_bytes": "进程读取量（字节）",
    "disk_write_bytes": "进程写入量（字节）",
    "source_sha256": "原始文件 SHA256",
    "restored_sha256": "恢复文件 SHA256",
    "source_md5": "原始文件 MD5",
    "restored_md5": "恢复文件 MD5",
    "verified_build_files": "已校验构建文件数",
    "bundle_version": "程序套件版本",
    "build_manifest_sha256": "构建清单 SHA256",
    "disk_free_bytes": "可用磁盘空间（字节）",
    "recovery_seconds": "恢复耗时（秒）",
    "chain_seconds": "链路总耗时（秒）",
    "effective_packets_per_second": "每秒唯一有效数据包",
    "effective_bytes_per_second": "合成视频链路有效速度（字节/秒）",
    "retransmit_seconds": "补传耗时（秒）",
    "loss_rate": "可控丢包比例",
    "displayed_frames": "GUI 已显示二维码帧数",
    "completed_cycles": "GUI 完成播放轮次",
    "elapsed_seconds": "实际持续时间（秒）",
    "duration_seconds": "配置持续时间（秒）",
    "qt_platform": "Qt 平台",
    "injected_http_503": "注入 HTTP 503 次数",
    "packets_persisted_before_exit": "退出前已持久化数据包",
    "renewal_observed": "已观察到续租",
    "lease_reallocated": "租约已重新分配",
    "decoded_qr_frames": "已解码合法二维码帧数",
    "sampled_video_frames": "已采样视频帧数",
    "unrecognized_sample_fraction": "未识别采样帧比例",
    "zxing_seconds": "合成 AVI 解码耗时（秒）",
    "decoded_qr_frames_per_second": "合成 AVI 解码吞吐量（二维码/秒）",
}


def write_reports(root: Path, report: dict) -> None:
    """仅写入调用者独占创建的报告目录，拒绝覆盖任何报告。"""
    counts = {state: sum(r["status"] == state for r in report["results"]) for state in LABELS}
    report["counts"] = counts
    required = {
        "environment",
        "encoder",
        "decoder",
        "control",
        "single",
        "dual",
        "missing",
        "fault",
    }
    passed = {r["id"] for r in report["results"] if r["status"] == "passed"}
    report["candidate_software_gate"] = required <= passed and not counts["failed"]
    report["hardware_accepted"] = False
    report["hardware_status"] = {
        "真实双机 SMB": "未验收",
        "真实屏幕录制": "未验收",
        "大视频可靠性": "未验收",
        "完整大文件二维码传输": "未验收",
    }
    report["unaccepted"] = [ITEMS[r["id"]] for r in report["results"] if r["status"] != "passed"]
    with (root / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with (root / "metrics.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["项目", "状态", "指标", "值", "证据"])
        for result in report["results"]:
            for key, value in result.get("metrics", {}).items():
                writer.writerow(
                    [
                        ITEMS[result["id"]],
                        LABELS[result["status"]],
                        METRICS.get(key, key),
                        value,
                        result.get("evidence", ""),
                    ]
                )
            if not result.get("metrics"):
                writer.writerow(
                    [
                        ITEMS[result["id"]],
                        LABELS[result["status"]],
                        "原因",
                        result.get("reason", ""),
                        result.get("evidence", ""),
                    ]
                )
    escaped = html.escape(json.dumps(report, ensure_ascii=False, indent=2))
    details = "".join(
        f"<h2>{ITEMS[r['id']]} · {LABELS[r['status']]}</h2><table>"
        + "".join(
            f"<tr><th>{html.escape(METRICS.get(key, key))}</th><td>{html.escape(str(value))}</td></tr>"
            for key, value in r.get("metrics", {}).items()
        )
        + "</table>"
        for r in report["results"]
        if r.get("metrics")
    )
    summary = " · ".join(
        f"{LABELS[state]} {counts[state]}" for state in ("passed", "failed", "skipped", "blocked")
    )
    gate = "满足" if report["candidate_software_gate"] else "未满足"
    metadata = html.escape(
        f"版本 {report.get('version', '未知')} · Commit {report.get('build_commit', '未知')} · "
        f"开始 {report.get('started_at', '未知')} · 结束 {report.get('ended_at', '未知')}"
    )
    rows = "".join(
        f"<tr><td>{ITEMS[r['id']]}</td><td>{LABELS[r['status']]}</td>"
        f"<td>{html.escape(r.get('reason', ''))}</td></tr>"
        for r in report["results"]
    )
    with (root / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<title>QRFT 中文验收报告</title><style>body{font:16px sans-serif;"
            "max-width:1100px;margin:32px auto;padding:16px}td,th{padding:10px;"
            "border:1px solid #ccc}table{border-collapse:collapse}pre{white-space:"
            "pre-wrap;overflow-wrap:anywhere}</style><h1>QRFT 验收报告</h1>"
            "<p>合成 AVI 和本地双进程不代表真实录屏或双机 SMB。"
            "大文件哈希指标不是二维码传输速度。</p>"
            f"<p>{metadata}</p><p>{summary}</p><p>软件候选版门禁：{gate}。真实硬件验收：未完成。</p>"
            f"<table><tr><th>项目</th><th>状态</th><th>说明</th></tr>{rows}</table>"
            f"{details}<details><summary>完整机器可读证据</summary><pre>{escaped}</pre></details></html>"
        )
