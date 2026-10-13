"""将 QRFT PNG 帧编码成无损 AVI 视频，供自动化闭环验收。"""

from __future__ import annotations

from itertools import chain
from pathlib import Path

from qrft.encoder_cli.main import export_frames


def export_video(
    source: Path,
    output: Path,
    *,
    chunk_size: int | None = None,
    fps: float | None = None,
    repeats: int | None = None,
    protocol_version: int = 1,
) -> Path:
    """使用 MJPG AVI 保留二维码图案；不依赖显示器或外部录屏软件。"""
    if protocol_version == 2:
        if fps not in (None, 20) or repeats not in (None, 1):
            raise ValueError("v2 video requires 20fps and one frame per scheduled display")
        from qrft.encoder_cli.playback import iter_encoded_frames

        return write_v2_video(
            iter_encoded_frames(source, protocol_version=2, chunk_size=chunk_size), output
        )
    chunk_size = 128 if chunk_size is None else chunk_size
    fps = 5.0 if fps is None else fps
    repeats = 3 if repeats is None else repeats
    if fps <= 0 or repeats < 1:
        raise ValueError("fps must be positive and repeats >= 1")

    import cv2
    import numpy as np

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    frames_dir = output.parent / (output.stem + "-frames")
    meta = export_frames(source, frames_dir, chunk_size=chunk_size)
    images = chain(
        [frames_dir / "00000000-start.png"],
        (frames_dir / f"{packet_id:08d}-data.png" for packet_id in range(meta["total_packets"])),
        [frames_dir / "99999999-finish.png"],
    )

    def load(path):
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

    first = load(frames_dir / "00000000-start.png")
    if first is None:
        raise OSError("cannot load START QR image")
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(
        str(output),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        writer.release()
        raise OSError(f"cannot create video: {output}")
    try:
        for path in images:
            image = load(path)
            if image is None:
                raise OSError(f"cannot read QR image: {path}")
            if image.shape[:2] != (height, width):
                image = cv2.resize(image, (width, height), interpolation=cv2.INTER_NEAREST)
            for _ in range(repeats):
                writer.write(np.ascontiguousarray(image))
    finally:
        writer.release()
    return output


def write_v2_video(frames, output: Path) -> Path:
    """Synthetic 20fps MJPG; center exact QR pixels, never resize to the START size."""
    import cv2
    import numpy as np

    from qrft.core.qr_image import v2_image

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    # Version40 with four quiet-zone modules and exact 50% scaling fits in 925px.
    side = 926  # Even codec dimensions; extra white pixel, QR unchanged.
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"), 20, (side, side))
    if not writer.isOpened():
        writer.release()
        raise OSError(f"cannot create v2 video: {output}")
    previous, image = None, None
    try:
        for _, raw in frames:
            if raw != previous:
                image = v2_image(raw)
                previous = raw
            canvas = np.full((side, side, 3), 255, dtype=np.uint8)
            h, w = image.shape[:2]
            if max(h, w) > side:
                raise ValueError("QR exceeds maximum canvas")
            y, x = (side - h) // 2, (side - w) // 2
            canvas[y : y + h, x : x + w] = image
            writer.write(canvas)
    finally:
        writer.release()
    return output
