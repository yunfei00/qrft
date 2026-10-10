# QRFT v1.0 — One-week delivery plan

Target: 2026-10-10 through 2026-10-16. Seven calendar days, aggressive target rather than guaranteed release.

| Date | Phase | Acceptance |
|---|---|---|
| 10/10 | Phase 0: repository, docs, protocol, CI | Reproducible repo baseline and binary QR test plan |
| 10/11 | Phase 1: core + CLI encoder | Arbitrary binary file displayed as numbered QR frames |
| 10/12 | Phase 2: video decoder + recovery | Recorded-video round trip, missing list, retransmission |
| 10/13 | Phase 3: web control center | EXE launches website; jobs, sessions and downloads |
| 10/14 | Phase 4: distributed worker | Two Windows workers read shared SMB video by logical time ranges |
| 10/15 | Phase 5: GUI encoder | GUI/CLI interoperability and four Windows packages |
| 10/16 | Phase 6: reliability, performance, release | Documented acceptance evidence and release artifacts |

Prioritize correctness and a usable end-to-end workflow. Do not claim large-video throughput, distributed scaling, or Windows packaging until measured. If schedule slips, publish exact unfinished items rather than inventing completion.

## Decisions
- New implementation; no legacy migration.
- Repository: public github.com/yunfei00/qrft.
- Four executable modules; one shared internal core.
- Windows LAN; one Windows video storage host; SMB direct video reads.
- Video files can be tens of GB; do not upload or replicate whole recordings.
- GitHub docs, tests, issues and commits are the source of truth, never chat history.
