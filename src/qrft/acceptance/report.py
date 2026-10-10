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
    "performance": "大文件哈希性能",
    "stability": "GUI 长时间稳定性",
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
                        key,
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
            f"<table><tr><th>项目</th><th>状态</th><th>说明</th></tr>{rows}</table>"
            f"<h2>完整证据与指标</h2><pre>{escaped}</pre></html>"
        )
