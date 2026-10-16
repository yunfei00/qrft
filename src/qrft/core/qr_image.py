"""Render v2 HEX frames with fixed QR parameters and automatic symbol version."""

from pathlib import Path

from .protocol import decode_frame


def v2_image(frame: bytes):
    """QR L, box size 10, border 4, then 50% nearest-neighbor scaling."""
    decode_frame(frame)
    import cv2
    import numpy as np
    import qrcode
    from qrcode.exceptions import DataOverflowError

    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4
    )
    qr.add_data(frame.decode("ascii"), optimize=0)
    try:
        qr.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        raise ValueError(
            "v2 QR capacity exceeded; shorten the filename or reduce chunk size"
        ) from exc
    pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bgr = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return cv2.resize(bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)


def render_png(frame: bytes, *, protocol_version=2, **options) -> bytes:
    if protocol_version != 2:
        raise ValueError("only protocol v2 is supported")
    if any(k not in {"correction", "box_size", "border"} for k in options):
        raise ValueError("unsupported v2 QR option")
    if any(
        options.get(k, value) != value
        for k, value in (("correction", "L"), ("box_size", 10), ("border", 4))
    ):
        raise ValueError("v2 requires correction L, box size 10, border 4")
    import cv2

    ok, png = cv2.imencode(".png", v2_image(frame))
    if not ok:
        raise OSError("cannot encode v2 QR PNG")
    return png.tobytes()


def qr_png(frame: bytes, **options) -> bytes:
    return render_png(frame, **options)


def save_qr_png(frame: bytes, destination: Path) -> None:
    destination.write_bytes(render_png(frame))
