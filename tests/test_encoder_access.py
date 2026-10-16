"""Development access, public usage help and optional operator-check regressions."""

import getpass
import subprocess
import sys

import pytest

from qrft.encoder_cli import access, entrypoint


def terminal(monkeypatch, capsys, inputs):
    monkeypatch.setattr(access, "PASSWORD_CHECK_ENABLED", True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    values = iter(inputs)
    calls = []

    def read(prompt):
        if not calls:
            assert capsys.readouterr() == ("", "")
        assert prompt == ""
        calls.append(True)
        return next(values)

    monkeypatch.setattr(getpass, "getpass", read)
    return calls


def test_correct_password_and_initial_silence(monkeypatch, capsys):
    calls = terminal(monkeypatch, capsys, ["qsnfj"])
    assert entrypoint.main([]) == 0
    assert len(calls) == 1
    assert "export" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments", [[], ["-h"], ["--help"], ["export", "--help"], ["play", "--unknown"], ["export"]]
)
def test_wrong_password_never_parses(monkeypatch, capsys, arguments):
    calls = terminal(monkeypatch, capsys, ["QSNFJ", "wrong", "qsnfJ"])
    assert entrypoint.main(arguments) == 1
    assert len(calls) == 3
    output = capsys.readouterr()
    assert not output.out
    assert "usage" not in output.err and "export" not in output.err
    assert "qsnfj" not in output.err and "QSNFJ" not in output.err


def test_retry_then_success(monkeypatch, capsys):
    calls = terminal(monkeypatch, capsys, ["wrong", "qsnfj"])
    assert entrypoint.main([]) == 0
    assert len(calls) == 2


@pytest.mark.parametrize("arguments", [["--unknown"], ["export"], ["play"]])
def test_reenabled_gate_invalid_parameters_show_usage(monkeypatch, capsys, arguments):
    terminal(monkeypatch, capsys, ["qsnfj"])
    assert entrypoint.main(arguments) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "usage" in output.err


@pytest.mark.parametrize("module", ["entrypoint", "main"])
def test_help_from_pipe_does_not_create_output(tmp_path, module):
    output = tmp_path / "never-created"
    command = [
        sys.executable,
        "-m",
        f"qrft.encoder_cli.{module}",
        *(["export"] if module == "entrypoint" else []),
        "unused",
        "--output",
        str(output),
        "--help",
    ]
    result = subprocess.run(command, input=b"", capture_output=True, timeout=15, check=False)
    assert result.returncode == 0
    assert b"usage" in result.stdout
    assert b"--output" in result.stdout
    assert not output.exists()


def test_getpass_cannot_fall_back_to_echo(monkeypatch, capsys):
    terminal(monkeypatch, capsys, [])

    def warning(prompt):
        import warnings

        warnings.warn("cannot hide", getpass.GetPassWarning)

    monkeypatch.setattr(getpass, "getpass", warning)
    assert entrypoint.main([]) == 1
    assert not capsys.readouterr().out


def test_pure_export_does_not_import_qt(tmp_path):
    pytest.importorskip("qrcode")
    source = tmp_path / "payload.bin"
    source.write_bytes(b"\x00\xff")
    # Isolated interpreter ensures imports from GUI tests cannot mask a CLI dependency.
    code = """import sys
import qrft.encoder_cli.entrypoint as cli
assert cli.main(sys.argv[1:]) == 0
assert not any(k.startswith("PySide6") for k in sys.modules)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            "export",
            str(source),
            "--protocol",
            "v2",
            "--output",
            str(tmp_path / "png"),
        ],
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows ConPTY test")
def test_real_windows_terminal_export_without_password(tmp_path):
    pytest.importorskip("winpty")
    pytest.importorskip("qrcode")
    pytest.importorskip("zxingcpp")
    import hashlib

    from encoder_console_driver import run_encoder

    from qrft.core.qr_decode import decode_qr_png
    from qrft.decoder.main import restore_video
    from qrft.encoder_cli.video_export import write_v2_video

    source = tmp_path / "中文,源.bin"
    source.write_bytes(bytes(range(256)) * 6)
    output = tmp_path / "frames"
    command = [
        sys.executable,
        "-m",
        "qrft.encoder_cli.entrypoint",
        "export",
        str(source),
        "--protocol",
        "v2",
        "--output",
        str(output),
    ]
    result = run_encoder(command)
    assert result.returncode == 0, result.stdout
    paths = [
        output / "00000000-start.png",
        *sorted(output.glob("*-data.png")),
        output / "99999999-finish.png",
    ]
    from qrft.core.protocol import serialize_frame

    frames = [("frame", serialize_frame(decode_qr_png(path.read_bytes()))) for path in paths]
    video = write_v2_video(frames, tmp_path / "console.avi")
    restored = restore_video(video, tmp_path / "task", protocol_version=2)
    assert (
        restored
        and hashlib.md5(restored.read_bytes()).digest() == hashlib.md5(source.read_bytes()).digest()
    )


def test_development_mode_never_reads_password_or_requires_tty(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    monkeypatch.setattr(
        getpass, "getpass", lambda *_: pytest.fail("password prompt in development")
    )
    assert access.PASSWORD_CHECK_ENABLED is False
    assert entrypoint.main([]) == 0
    output = capsys.readouterr()
    assert "--help" in output.out and "2100" in output.out
    assert not output.err


@pytest.mark.parametrize(
    "arguments", [["--help"], ["info", "--help"], ["export", "--help"], ["play", "--help"]]
)
def test_development_help_is_available_without_password(arguments, capsys):
    with pytest.raises(SystemExit) as raised:
        entrypoint.main(arguments)
    assert raised.value.code == 0
    output = capsys.readouterr()
    assert "usage" in output.out and not output.err
    if len(arguments) > 1:
        assert "--chunk-size" in output.out
