"""Drive the encoder through a real Windows ConPTY."""

import os
import subprocess
import threading
import time


def run_encoder(command, *, cwd=None, env=None, timeout=120, check_cancel=None, inputs=()):
    from winpty import PtyProcess

    process = PtyProcess.spawn(
        list(map(str, command)),
        cwd=str(cwd) if cwd else None,
        env=dict(os.environ if env is None else env),
    )
    chunks = []

    def collect():
        try:
            while True:
                chunks.append(process.read())
        except (EOFError, OSError):
            pass

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + timeout
        # Native terminal keystrokes; getpass disables echo when it reads them.
        time.sleep(0.5)
        for value in inputs:
            if process.isalive():
                process.write(value + "\r")
                time.sleep(0.15)
        while process.isalive():
            if check_cancel:
                check_cancel()
            if time.monotonic() >= deadline:
                raise TimeoutError("交互式编码器测试超时")
            time.sleep(0.05)
        reader.join(timeout=2)
        output = "".join(chunks)
        for value in inputs:
            if value:
                output = output.replace(value, "[测试输入已隐藏]")
        return subprocess.CompletedProcess(command, process.exitstatus, stdout=output, stderr="")
    finally:
        process.close(force=True)
        reader.join(timeout=2)
