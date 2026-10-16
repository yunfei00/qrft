"""V2 video export for decoder integration and recorded-video checks."""

from __future__ import annotations

from pathlib import Path


def export_video(
    source: Path,
    output: Path,
    *,
    chunk_size: int | None = None,
    fps: float | None = None,
    repeats: int | None = None,
    protocol_version: int = 2,
) -> Path:
    """Encode the scheduled V2 stream at 20 fps, including repeated controls."""
    if protocol_version != 2:
        raise ValueError("only protocol v2 is supported")
    if fps not in (None, 20) or repeats not in (None, 1):
        raise ValueError("v2 video requires 20fps and one frame per scheduled display")
    from qrft.encoder_cli.playback import iter_encoded_frames

    frames = iter_encoded_frames(source, chunk_size=chunk_size)
    try:
        return write_v2_video(frames, output)
    finally:
        frames.close()


def write_v2_video(frames, output: Path) -> Path:
    """Synthetic 20fps MJPG; center exact QR pixels without resizing."""
    import cv2
    import numpy as np

    from qrft.core.qr_image import v2_image

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    side = 926  # Even codec dimensions, accommodating a 925px version-40 QR.
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
