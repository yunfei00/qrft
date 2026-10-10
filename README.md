# QRFT — QR File Transfer

Universal binary file transfer via displayed QR codes, recorded video and distributed Windows decoding.

**Status:** Phase 0; software not implemented yet. **Target:** 2026-10-16 (aggressive seven-day plan).

## Start here
- [Current status and next action](docs/STATUS.md)
- [Seven-day plan](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [QR binary protocol draft](docs/PROTOCOL.md)
- [Acceptance criteria](docs/ACCEPTANCE.md)
- [Development rules](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Four Windows executables
1. `QRFT-Encoder-CLI.exe` — command-line file encoder and fullscreen QR display.
2. `QRFT-Encoder-GUI.exe` — graphical file encoder.
3. `QRFT-Decoder.exe` — headless distributed video decoding worker.
4. `QRFT-Control.exe` — web control center, task scheduler and recovery service.

## Operating environment
All decoder servers run Windows on one LAN. Recordings can be tens of GB and are stored on one Windows machine. Workers read video via SMB in logical time segments, without downloading the whole recording. Results are centrally merged and missing packet lists are generated for retransmission.

## Project rule
**GitHub is the single source of truth.** Requirements, design decisions, test evidence, progress, blockers and next steps must be committed here. Never rely on ChatGPT conversation history.

No proprietary files, recordings, credentials or production configurations belong in this public repository.

## License
Not yet selected. Public visibility does not automatically grant reuse rights.

## Python development environment
Python 3.12 with **uv** for environment, dependencies, lockfile and commands. See [uv development setup](docs/DEVELOPMENT.md). The Windows CI scaffold is in [ci.yml](.github/workflows/ci.yml).
