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
