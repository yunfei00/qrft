"""真实 SMB 角色：使用 Windows MachineGuid 的散列区分主机，不记录凭据。"""

import hashlib
import platform
import time
from pathlib import Path
from urllib.parse import urlsplit


class Blocked(Exception):
    pass


def machine_id():
    if platform.system() != "Windows":
        raise Blocked("SMB 角色要求 Windows")
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Cryptography",
        access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
    ) as key:
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
    return hashlib.sha256(value.encode()).hexdigest()


def register(runner, node, video):
    if not str(video).startswith("\\\\") or not Path(video).is_file():
        raise Blocked("必须提供本机可直接读取的 UNC 视频路径；请通过 Windows 建立 SMB 访问")
    runner.api(
        "/acceptance/nodes",
        {
            "node_id": node,
            "machine_id": machine_id(),
            "hostname": platform.node(),
            "video_path": str(video),
        },
    )


def worker_role(runner):
    url = urlsplit(runner.smb_server)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise Blocked("控制中心地址应为 HTTP(S) 地址，不得包含凭据、Token 或查询参数")
    runner.base = runner.smb_server.rstrip("/")
    node = "smb-" + machine_id()[:16]
    video = runner.smb_video
    if runner.api("/health").get("acceptance_instance") != Path(video).parent.name:
        raise Blocked("该地址不是本次 UNC 视频对应的独占验收控制中心，未登记或领取任务")
    runner.expected_instance = Path(video).parent.name
    runner.env["QRFT_ACCEPTANCE_ID"] = runner.expected_instance
    register(runner, node, video)
    runner.log(f"SMB 节点 {node} 已验证 UNC 访问，正在等待控制机登记视频")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        runner.check()
        videos = runner.api("/videos")
        matches = [v for v in videos if v["path"] == video]
        if matches:
            task = matches[-1]["task_id"]
            started = time.monotonic()
            runner.run(
                "QRFT-Decoder", "worker", "--server", runner.base, "--node-id", node, "--once"
            )
            slices = [s for s in runner.api("/slices") if s["owner"] == node]
            if not slices or not all(s["state"] == "done" for s in slices):
                raise Blocked("当前节点没有完成时间片；不能宣称双机通过")
            evidence = {
                "machine_id": machine_id(),
                "node_id": node,
                "task_id": task,
                "slices": slices,
                "seconds": time.monotonic() - started,
            }
            runner.evidence("smb-worker.json", evidence)
            # 节点角色无法单独证明中心最终 SHA256 与断线恢复。
            raise Blocked("节点时间片完成，证据已保存；最终验收须查看控制机报告")
        runner.pause(0.5)
    raise Blocked("10 分钟内没有控制机登记对应 UNC 视频")


def controller_role(runner):
    import shutil

    shared = Path(runner.smb_share)
    if not str(shared).startswith("\\\\") or not shared.is_dir():
        raise Blocked("真实双机 SMB：未验收；需要可访问的 UNC 共享目录与第二台 Windows")
    runner.ensure_video()
    # 只创建自己的新目录，不改动共享目录里的已有文件；保留证据供另一机器读取。
    folder = shared / runner.root.name
    folder.mkdir(exist_ok=False)
    video = folder / "验收视频.avi"
    shutil.copyfile(runner.video, video)
    runner.control()
    node = "smb-" + machine_id()[:16]
    register(runner, node, video)
    runner.log(f"Worker B 请连接控制机端口 {runner.smb_port}，UNC 视频：{video}")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        nodes = [
            n
            for n in runner.api("/acceptance/nodes")
            if n["video_path"] == str(video) and n["registered_at"] > time.time() - 600
        ]
        if len({n["machine_id"] for n in nodes}) >= 2:
            break
        runner.pause(0.5)
    else:
        raise Blocked("真实双机 SMB：未验收；未检测到不同 Windows 主机的 UNC 访问证据")
    task, vid = runner.task(video, 42)
    runner.run("QRFT-Decoder", "worker", "--server", runner.base, "--node-id", node, "--once")
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        slices = runner.api(f"/slices?video_id={vid}")
        if all(s["state"] == "done" for s in slices):
            break
        runner.pause(0.5)
    else:
        raise Blocked("远程时间片未完成；检查远程节点日志与 SMB 连接")
    identities = {n["node_id"]: n["machine_id"] for n in nodes}
    if len({identities.get(s["owner"]) for s in slices} - {None}) < 2:
        raise Blocked("不同时间片未由两个不同主机完成")
    recovery = runner.recover(task)
    runner.evidence(
        "smb-controller.json",
        {
            "nodes": nodes,
            "slices": slices,
            "recovery": recovery,
            "worker_metrics": runner.api(f"/acceptance/slices?video_id={vid}"),
        },
    )
    raise Blocked(
        "真实双机基础 SHA256 恢复通过；远程断线/重新连接尚需人工执行，完整 SMB 验收未通过"
    )
