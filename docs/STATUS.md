# QRFT status / handoff

Last updated: 2026-10-10.
Current stage: Phase 0.
Target: 2026-10-16.
Application status: **not implemented or verified**.

## Completed
- Public repository established.
- Seven-day schedule, architecture and protocol draft documented.

## Not yet verified
- Windows CI.
- QR raw-byte interoperability.
- CLI encoder, decoder, web center, worker, GUI.
- Large-video benchmarks and Windows EXE packages.

## Next action
Create source/package skeleton and Windows CI, then implement binary QR test vectors and freeze protocol.

## Handoff rules
Update this document after every milestone with: implemented files and commit SHA, exact tests/commands/results, blockers, next action, and decision links. A new assistant or developer should read README.md, STATUS.md, ROADMAP.md, ARCHITECTURE.md, PROTOCOL.md before continuing. Chat history is not authoritative.

## Latest update — uv scaffold
- Added `pyproject.toml`, `.python-version` (3.12), shared source package skeleton and starter pytest.
- Added Windows GitHub Actions workflow using `astral-sh/setup-uv`.
- Added `docs/DEVELOPMENT.md` with Windows setup and uv dependency commands.
- **Not yet verified:** CI execution, dependency resolution, uv.lock, Windows EXE builds, any protocol functionality.
- **Next:** generate and commit uv.lock using uv; change CI to `uv sync --locked`; inspect first Windows CI run; implement binary QR test vectors.
