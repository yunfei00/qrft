# QRFT wire protocol v1 — DRAFT

**Do not implement independent encoder/decoder releases before byte-level fixtures freeze this protocol.**

## Fixed requirements
- QR content is raw binary bytes; never coerce to UTF-8 or Base64.
- Each QR frame ends with **8 ASCII decimal digits** identifying its packet.
- Reserved IDs: `88888888` START; `99999999` FINISH.
- DATA packets use zero-based 8-digit decimal IDs, excluding reserved values.
- Stream arbitrary files without loading entire content into RAM.
- Retransmission uses original chunk size and packet numbering.
- START includes filename, file size, MD5, SHA-256, chunk size, total count, version and stable file/session identity.
- FINISH means sending ended, not that recovery is verified.

## Proposed DATA bytes
```text
[payload: raw bytes][CRC32: 4 bytes][packet ID: 8 ASCII digits]
```
CRC coverage and byte order still require explicit test vectors. Last packet may be shorter. Binary-safe QR decoding is mandatory.

## Missing list
TXT lines may be individual 8-digit packet IDs or inclusive ranges, e.g.:
```text
00000001
00000100-00000150
```
CSV and JSON exports require documented schemas. Invalid, reserved and out-of-range IDs must be rejected.

## D1 decisions to freeze
- QR version, error correction and safe payload size in recorded video.
- Control-frame serialization and handling metadata larger than a single QR.
- Session binding for sparse retransmission, whose DATA frames lack session ID.
- CRC32 endianness and covered bytes; byte-exact fixtures.
- Empty files, max packet number, START replay, incomplete recording and packet conflicts.

## Acceptance
Round-trip fixtures must include embedded NUL, non-UTF8, Unicode filename, empty file, random bytes, corruption and duplicates. Final reconstructed bytes must match original SHA-256 and MD5.

## Current reference implementation (2026-10-10)
The first draft implementation is in `src/qrft/core/protocol.py`.
- CRC32 is big-endian and covers `body || 8-digit packet ID`.
- START body is `QRFT1S || UTF-8 compact JSON`.
- FINISH body is `QRFT1F`.
- DATA body is the original file bytes (without transformation).
- All frames end in their 8-digit ASCII packet ID.
These choices are **provisional** pending QR-image roundtrip and interoperability tests. START JSON is not yet split across multiple QR symbols, and session binding for orphan DATA frames remains unresolved. Do not treat protocol v1 as frozen.
