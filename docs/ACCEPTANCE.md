# Acceptance checklist

- Arbitrary bytes: empty, one byte, chunk boundary, random binary, NUL, non-UTF8, Unicode filename, no extension.
- Binary QR encode/decode and actual recorded-video recovery, whole-file SHA-256/MD5 verification.
- Corrupt, duplicate, out-of-order, conflicting and missing packets.
- Always write missing.txt, missing.csv and missing.json after decode attempt.
- Sparse retransmission and merge into original session.
- Worker crash/restart, lease expiry, reconnect, idempotent merge.
- Two Windows workers reading one shared large video by time ranges without copying entire video.
- Verify segment boundary overlap and keyframe seek.
- Control EXE starts browser UI; workers connect and authenticate.
- Four packaged Windows programs with no separately installed Python or Node.
- Measure FPS, packets/sec, RAM peak, disk and SMB throughput on a tens-of-GB recording.
- Document actual test evidence, remaining failures and limitations.
