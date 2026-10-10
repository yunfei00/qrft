# Development and documentation rules

GitHub is the single source of truth. Every phase updates code, tests, docs/STATUS.md and CHANGELOG.md.

- No feature is marked done without reproducible test evidence.
- Maintain four user-facing executables and a shared internal core.
- Keep commits small, CI passing and tests deterministic.
- Never commit tokens, actual recordings, private files or production configuration.
- Record important architectural decisions in docs/ and changes in CHANGELOG.md.
- Each handoff documents exact current status, blockers and next executable task.
- Use a Windows runner for EXE builds and smoke tests.

To resume after any interruption: read README.md, docs/STATUS.md, docs/ROADMAP.md, docs/ARCHITECTURE.md and docs/PROTOCOL.md. Do not depend on chat transcripts.

## User-side operation policy
Before requesting any manual operation, write its exact PowerShell commands, prerequisites, expected results and status to [docs/USER_ACTIONS.md](docs/USER_ACTIONS.md). Prefer CI/automated validation; never rely on chat history for user operations.
