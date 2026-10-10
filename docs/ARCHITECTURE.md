# QRFT architecture

QRFT transfers **arbitrary binary files**, not any particular engineering file format.

## Four deliverables
1. `QRFT-Encoder-CLI.exe`: command-line file selection and controls, fullscreen QR display, selective retransmission.
2. `QRFT-Encoder-GUI.exe`: PySide6 desktop encoder using the same core.
3. `QRFT-Decoder.exe`: headless Windows worker; register, heartbeat, lease and decode time-range tasks.
4. `QRFT-Control.exe`: bundled web server + UI, coordinator, packet merger and recovery.

## Topology
One Windows host stores recordings (potentially 10s of GB), exposing read-only SMB share to decoding workers. Control center registers video path without copying the recording. Workers poll authenticated HTTP API for logical time ranges, seek/decode using FFmpeg, crop QR ROI, identify valid packets and upload **batched** packet results. Control center stores packet blobs on disk, metadata in SQLite, deduplicates and merges sessions, exports missing packet lists, and verifies recovered file hash.

## Reliability
- Bounded memory for encoder pre-rendering and worker decoding.
- Keyframe-aware video seeking and overlapping time-range boundaries.
- Task lease expiry and retry, heartbeat, idempotent result commit.
- Conflicting packet bytes quarantined rather than overwritten.
- START metadata binds video data to session; orphan packets quarantined.
- Every decode attempt updates missing.txt, missing.csv, missing.json.
- Recovery is complete only when expected packet set is present and whole-file hashes match.
- SMB disk/network throughput and decoding throughput measured before tuning parallelism.

## Security
Public repo: no credentials, production recordings, proprietary files or real infrastructure config. Restrict SMB permissions; use per-node API tokens and LAN firewall restrictions.

## Planned stack
Python 3.12, pytest, PySide6, FastAPI, FFmpeg/ffprobe, binary-safe QR encoder/decoder, React, PyInstaller onedir, Windows GitHub Actions. Dependencies are provisional until binary QR interoperability tests pass.
