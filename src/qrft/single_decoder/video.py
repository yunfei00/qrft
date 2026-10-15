"""Sequential all-frame decoding. Every barcode in every frame is considered."""

import hashlib
import math


def fingerprint(path):
    before = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise OSError("Video changed during identity check")
    return after.st_size, after.st_mtime_ns, digest


def frames(path):
    import cv2
    import zxingcpp

    capture = None
    try:
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise OSError("Cannot open video")
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        total = int(count) if math.isfinite(count) and 0 < count < 1e12 else None
        index = 0
        while True:
            ok, image = capture.read()
            if not ok:
                if not index or (total is not None and index < total):
                    raise OSError(f"Video read ended early at frame {index}; declared {total}")
                return
            index += 1
            try:
                codes = [bytes(result.bytes) for result in zxingcpp.read_barcodes(image)]
                yield index, total, codes, None
            except (RuntimeError, ValueError, TypeError) as exc:
                yield index, total, [], f"Barcode recognition failed: {exc}"
    except cv2.error as exc:
        raise OSError(f"OpenCV video read failure: {exc}") from exc
    finally:
        if capture is not None:
            capture.release()
