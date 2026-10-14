"""Independent QRFT2100 wire, raster, source, terminal and playback regressions."""

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import zxingcpp
from PIL import Image

from qrft.encoder2100 import cli, encoder
from qrft.encoder2100.encoder import Source, export, select
from qrft.encoder2100.player import QR_SIZE, QR_X, QR_Y, Frames, KeyEdge, State, canvas
from qrft.encoder2100.protocol import FINISH_ID, START_ID, data_frame, inspect_frame
from qrft.encoder2100.qr import image, png, qr_code


def independently_read(picture):
    decoded = zxingcpp.read_barcode(picture)
    assert decoded is not None
    text = decoded.text
    assert set(text) <= set("0123456789ABCDEF")
    content = bytes.fromhex(text[:-48])
    assert text[-48:-16] == hashlib.md5(content).hexdigest().upper()
    number = bytes.fromhex(text[-16:])
    assert len(number) == 8 and number.isdigit()
    return int(number), content


@pytest.mark.parametrize("size", [1, 100, 1400, 2099, 2100])
@pytest.mark.parametrize("kind", ["zero", "ff", "cycle", "random"])
def test_actual_full_density_png(size, kind):
    data = {
        "zero": b"\x00" * size,
        "ff": b"\xff" * size,
        "cycle": (bytes(range(256)) * 9)[:size],
        "random": os.urandom(size),
    }[kind]
    text = data_frame(data, 7)
    qr = qr_code(text)
    from qrcode.constants import ERROR_CORRECT_L
    from qrcode.util import MODE_ALPHA_NUM

    assert qr.version == 40 and qr.error_correction == ERROR_CORRECT_L
    assert qr.box_size == 5 and qr.border == 4 and len(qr.modules) == 177
    assert len(qr.data_list) == 1 and qr.data_list[0].mode == MODE_ALPHA_NUM
    assert len(text) == size * 2 + 48
    picture = Image.open(io.BytesIO(png(text)))
    pixels = np.asarray(picture)
    assert picture.size == (925, 925) and set(np.unique(pixels)) == {0, 255}
    assert np.all(pixels[:20] == 255) and np.all(pixels[-20:] == 255)
    assert np.all(pixels[:, :20] == 255) and np.all(pixels[:, -20:] == 255)
    assert np.array_equal(pixels, np.repeat(np.repeat(pixels[::5, ::5], 5, 0), 5, 1))
    assert independently_read(picture) == (7, data)


def test_actual_capacity_boundary():
    assert qr_code("A" * 4296).version == 40
    with pytest.raises(ValueError, match="容量溢出"):
        qr_code("A" * 4297)
    with pytest.raises(ValueError):
        data_frame(bytes(2101), 0)


def test_zero_safe_codewords_equal_reference():
    from qrcode.util import create_data

    for size in (1, 100, 1400, 2100):
        qr = qr_code(data_frame(os.urandom(size), 0))
        assert qr.data_cache == create_data(qr.version, qr.error_correction, qr.data_list)


@pytest.mark.parametrize("size", [0, 1, 2100, 2101, 4301])
@pytest.mark.parametrize("name", ["中文,MiX.bin", "noextension"])
def test_source_control_order_and_png_recovery(tmp_path, size, name):
    path = tmp_path / name
    original = (bytes(range(256)) * 18)[:size]
    path.write_bytes(original)
    source = Source(path)
    ranges = select(source.metadata.packets)
    frames = list(source.frames(ranges))
    assert [i for i, _ in frames[:20]] == [START_ID] * 20
    assert [i for i, _ in frames[-20:]] == [FINISH_ID] * 20
    assert len(frames) == source.metadata.packets + 40
    result = export(source, tmp_path / "png", ranges)
    assert result["complete"]
    start = independently_read(Image.open(tmp_path / "png" / "88888888.png"))[1]
    assert start.decode().rsplit(",", 3) == [
        name,
        hashlib.md5(original).hexdigest().upper(),
        str(source.metadata.packets),
        "QRFT2100",
    ]
    assert independently_read(Image.open(tmp_path / "png" / "99999999.png")) == (
        FINISH_ID,
        b"finish",
    )
    recovered = b"".join(
        independently_read(Image.open(tmp_path / "png" / f"{i:08d}.png"))[1]
        for i in range(source.metadata.packets)
    )
    assert recovered == original


def test_missing_ranges_and_identical_reencoding(tmp_path):
    path = tmp_path / "sample"
    path.write_bytes(os.urandom(8401))
    source = Source(path)
    missing = tmp_path / "missing.txt"
    missing.write_text("3\n1-2\n00000001\n# comment\n", encoding="utf-8-sig")
    ranges = select(5, missing=missing)
    assert ranges == [(1, 3)]
    full = dict(source.frames(select(5), repeat_controls=False))
    subset = dict(source.frames(ranges, repeat_controls=False))
    assert set(subset) == {START_ID, FINISH_ID, 1, 2, 3}
    assert all(full[i] == subset[i] for i in subset)
    assert list(source.frames(ranges)) == list(source.frames(ranges))
    assert png(full[1]) == png(subset[1])
    assert select(5, 2, 2, missing) == [(2, 2)]
    for text in ("5", "2-1", "bad", "99999999", "-1"):
        missing.write_text(text)
        with pytest.raises(ValueError):
            select(5, missing=missing)


def test_invalid_wire_and_capacity():
    good = data_frame(bytes(range(256)), 0)
    for bad in (good.lower(), good[:-1], "Z" + good[1:], "F" + good[1:], good[:-16] + "FF" * 8):
        with pytest.raises(ValueError):
            inspect_frame(bad)
    with pytest.raises(ValueError):
        data_frame(b"x", START_ID)
    with pytest.raises(ValueError, match="容量溢出"):
        encoder.Metadata("中" * 800, 0, "A" * 32, 0).start() and qr_code(
            encoder.Metadata("中" * 800, 0, "A" * 32, 0).start()
        )


def test_export_interrupt_disk_permission_and_protection(tmp_path, monkeypatch):
    path = tmp_path / "source"
    path.write_bytes(os.urandom(4201))
    source = Source(path)
    ranges = select(3)
    protected = tmp_path / "protected"
    protected.mkdir()
    (protected / "keep").write_bytes(b"KEEP")
    with pytest.raises(FileExistsError):
        export(source, protected, ranges)
    assert (protected / "keep").read_bytes() == b"KEEP"
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls > 6

    source.cancelled = cancel
    with pytest.raises(InterruptedError):
        export(source, tmp_path / "cancel", ranges)
    assert not (tmp_path / "cancel" / "manifest.json").exists()
    assert "incomplete" in (tmp_path / "cancel" / "operations.jsonl").read_text()
    source.cancelled = None
    monkeypatch.setattr(encoder.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(OSError, match="磁盘空间不足"):
        export(source, tmp_path / "disk-full", ranges)
    assert not list((tmp_path / "disk-full").glob("*.png"))
    with pytest.raises(FileNotFoundError):
        Source(tmp_path / "absent")
    with pytest.raises(ValueError):
        Source(tmp_path)
    with pytest.raises(OSError):
        export(source, path / "bad", ranges)
    original_open = Path.open

    def denied(self, *args, **kwargs):
        if self.name == "operations.jsonl":
            raise PermissionError("injected OS permission failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError):
        export(source, tmp_path / "permission", ranges)
    assert not list((tmp_path / "permission").glob("*.png"))
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="改变"):
        list(source.frames(ranges))


def test_playback_state_and_fixed_canvas():
    state = State(0.05)
    assert not state.due(10000) and state.status == "READY"
    state.space(0)
    assert not state.due(0.049) and state.due(0.05)
    state.space(0.1)
    assert state.status == "PAUSED" and not state.due(10)
    state.space(20)
    assert state.status == "PLAYING" and state.due(20.1)
    state.status = "FINISHED"
    state.space(30)
    assert state.status == "FINISHED" and not state.due(40)
    data = os.urandom(2100)
    picture = image(data_frame(data, 0))
    for label, status in [(START_ID, "READY"), (0, "PLAYING"), (FINISH_ID, "FINISHED")]:
        result = canvas(picture, label, status, 1, 41)
        region = result[QR_Y : QR_Y + QR_SIZE, QR_X : QR_X + QR_SIZE]
        assert result.shape == (1010, 945, 3)
        assert np.array_equal(region, np.asarray(picture)[:, :, ::-1])
        assert independently_read(region) == (0, data)


def test_bounded_process_prefetch():
    frames = Frames(((i, data_frame(b"test", i)) for i in range(30)), 3)
    try:
        frames.fill()
        assert len(frames.queue) == 3
        assert frames.queue[0][1].result(timeout=30).size == (925, 925)
        frames.fill()
        assert len(frames.queue) == 3
    finally:
        frames.close()


def test_windows_short_tap_and_hold_edges():
    latch = KeyEdge()
    assert latch.press(32, 0, down=False)
    assert not latch.press(-1, 0.1, down=False)
    assert latch.press(-1, 0.5, down=True)
    for now in (0.6, 1, 2):
        assert not latch.press(32, now, down=True)
    assert not latch.press(-1, 2.1, down=False)
    assert latch.press(32, 2.5, down=False)
    assert not latch.press(32, 3, down=True, focused=False)


def test_cancel_hashing_before_any_export(tmp_path):
    source = tmp_path / "input"
    source.write_bytes(b"test")
    with pytest.raises(InterruptedError):
        Source(source, cancelled=lambda: True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input"]


@pytest.mark.parametrize("mode", ["escape", "window-close", "interrupt"])
def test_player_early_exit_closes_owned_resources(tmp_path, monkeypatch, mode):
    import cv2

    from qrft.encoder2100 import player

    path = tmp_path / "source"
    path.write_bytes(b"sample")
    closed = []

    class Pending:
        def __init__(self, frames, capacity):
            self.frames = frames

        def fill(self):
            pass

        def close(self):
            self.frames.close()
            closed.append("prefetch")

    def wait(_):
        if mode == "interrupt":
            raise KeyboardInterrupt
        return 27 if mode == "escape" else -1

    monkeypatch.setattr(player, "Frames", Pending)
    monkeypatch.setattr(player, "windows_desktop", lambda _: (None, None))
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(cv2, "waitKey", wait)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 0 if mode == "window-close" else 1)
    monkeypatch.setattr(cv2, "destroyWindow", lambda *args: closed.append("window"))
    if mode == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            player.play(Source(path), [(0, 0)], log_path=tmp_path / "player.log")
    else:
        assert player.play(Source(path), [(0, 0)], log_path=tmp_path / "player.log") == 130
    assert closed == ["prefetch", "window"]


@pytest.mark.parametrize("arguments", [[], ["-h"], ["--help"], ["--bad"], ["export"]])
def test_gate_precedes_parser_and_has_no_initial_output(monkeypatch, capsys, arguments):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    def getpass(prompt):
        assert prompt == ""
        assert capsys.readouterr() == ("", "")
        return "qsnfj"

    monkeypatch.setattr(cli.getpass, "getpass", getpass)
    assert cli.main(arguments) == (0 if not arguments else 2)
    output = capsys.readouterr()
    assert "usage:" not in output.err and "qsnfj" not in output.err


@pytest.mark.parametrize(
    "values,accepted",
    [(["qsnfj"], True), (["QSNFJ"] * 3, False), (["bad"] * 3, False), (["bad", "qsnfj"], True)],
)
def test_gate_retry_limit(monkeypatch, values, accepted):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    iterator = iter(values)
    calls = []

    def getpass(_):
        calls.append(1)
        return next(iterator)

    monkeypatch.setattr(cli.getpass, "getpass", getpass)
    assert cli.authenticate() is accepted
    assert len(calls) == len(values)


def test_pipe_denied_and_no_system_imports(tmp_path):
    command = [
        sys.executable,
        "-m",
        "qrft.encoder2100.cli",
        "export",
        "absent",
        "--output",
        str(tmp_path / "no"),
    ]
    result = subprocess.run(
        command, input="qsnfj\n", capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 1 and not (tmp_path / "no").exists()
    assert "usage:" not in result.stdout + result.stderr
    script = "import sys; from qrft.encoder2100 import cli; assert not any(x.startswith(('PySide6','cv2','qrft.decoder','qrft.control','qrft.worker','qrft.encoder_gui')) for x in sys.modules)"
    subprocess.run([sys.executable, "-c", script], check=True, timeout=20)


def test_real_cli_gate_export_and_help(tmp_path):
    # Reuse only the test-only ConPTY adapter, never an old encoder implementation.
    from qrft.encoder_cli.console_test import run_encoder

    source = tmp_path / "中文,MiX.bin"
    source.write_bytes(os.urandom(2101))
    command = [sys.executable, "-m", "qrft.encoder2100.cli"]
    output = tmp_path / "out"
    result = run_encoder([*command, "export", str(source), "--output", str(output)], timeout=40)
    assert result.returncode == 0, result.stdout
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["packets"] == 2
    wrapper = "from qrft.encoder2100.cli import main; r=main(); import sys; assert not any(x.startswith(('PySide6','cv2','qrft.decoder','qrft.control','qrft.worker','qrft.encoder_gui')) for x in sys.modules); sys.exit(r)"
    result = run_encoder(
        [
            sys.executable,
            "-c",
            wrapper,
            "export",
            str(source),
            "--output",
            str(tmp_path / "isolated"),
        ],
        timeout=40,
    )
    assert result.returncode == 0, result.stdout
    for flag in ("-h", "--help", "--bad"):
        result = run_encoder([*command, flag], timeout=20)
        assert result.returncode == 2 and "usage:" not in result.stdout
    rejected = tmp_path / "rejected"
    result = run_encoder(
        [*command, "export", str(source), "--output", str(rejected)], inputs=("QSNFJ", "bad", "bad")
    )
    assert result.returncode == 1 and not rejected.exists()
