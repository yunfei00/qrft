"""Local operator check; this is not a security or licensing boundary."""

import getpass
import hmac
import sys
import warnings


def authenticate() -> bool:
    """Require a real terminal and hidden input before any application output."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("需要交互式终端，已拒绝运行。", file=sys.stderr)
        return False
    for _ in range(3):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                entered = getpass.getpass("")
        except (EOFError, KeyboardInterrupt, OSError, getpass.GetPassWarning):
            print("交互校验已取消。", file=sys.stderr)
            return False
        try:
            if hmac.compare_digest(entered.encode("utf-8"), b"qsnfj"):
                return True
        except UnicodeError:
            pass
        print("校验未通过。", file=sys.stderr)
    print("重试次数已用完，已拒绝运行。", file=sys.stderr)
    return False


class SilentArgumentParserMixin:
    def error(self, message):
        raise ValueError("参数无效，请参考编码器操作文档。")
