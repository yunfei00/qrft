# Changelog

## Unreleased
- Initialized the public QRFT repository documentation baseline.
- Established four deliverables, Windows LAN + SMB architecture, one-week schedule and GitHub-only handoff discipline.

No functional application implementation is claimed yet.

### Core implementation
- Added first binary frame encoder/decoder with CRC32 and fixed-width ASCII packet IDs.
- Added file manifest hashing, chunk reads and retransmission packet-list parser.
- Added unit tests (not yet verified by CI).
