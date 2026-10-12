"""Windows test driver: type into a real ConPTY, never pipe stdin or bypass the gate.

Only used by explicit automated acceptance/build tests. Ordinary encoder entrypoints
do not import or call this driver. Terminal input is deliberately excluded from logs.
"""

import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _native_console():
    """A windowed test host may have null Windows handles; never hide a user's console."""
    attached = False
    kernel32 = None
    if getattr(sys, "frozen", False):
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = [ctypes.c_ulong]
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        output_handle = kernel32.GetStdHandle(0xFFFFFFF5)  # STD_OUTPUT_HANDLE
        if output_handle in (None, ctypes.c_void_p(-1).value):
            if kernel32.AttachConsole(0xFFFFFFFF):
                attached = True
            elif kernel32.AllocConsole():
                attached = True
                user32 = ctypes.windll.user32
                kernel32.GetConsoleWindow.restype = ctypes.c_void_p
                user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
                user32.ShowWindow(kernel32.GetConsoleWindow(), 0)
            else:
                raise OSError("无法建立验收驱动的原生终端")
    try:
        yield
    finally:
        if attached:
            kernel32.FreeConsole()


def run_encoder(command, *, cwd=None, env=None, timeout=120, check_cancel=None, inputs=("qsnfj",)):
    with _native_console():
        return _run_encoder(
            command, cwd=cwd, env=env, timeout=timeout, check_cancel=check_cancel, inputs=inputs
        )


def _run_encoder(command, *, cwd, env, timeout, check_cancel, inputs):
    from winpty import PtyProcess

    child_env = dict(os.environ if env is None else env)
    if getattr(sys, "frozen", False):
        import winpty

        if not (Path(winpty.__file__).parent / "OpenConsole.exe").is_file():
            raise FileNotFoundError("验收构建缺少 pywinpty OpenConsole.exe，请使用完整新构建")
        # The acceptance EXE must launch an independent application, not a child
        # inheriting its PyInstaller bootloader/library-search context.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        previous = ctypes.create_unicode_buffer(32768)
        kernel32.GetDllDirectoryW(len(previous), previous)
        child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        kernel32.SetDllDirectoryW(None)
        try:
            process = PtyProcess.spawn(
                list(map(str, command)), cwd=str(cwd) if cwd else None, env=child_env
            )
        finally:
            kernel32.SetDllDirectoryW(previous.value or None)
    else:
        process = PtyProcess.spawn(
            list(map(str, command)), cwd=str(cwd) if cwd else None, env=child_env
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
