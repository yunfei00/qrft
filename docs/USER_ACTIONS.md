# User actions — copy/paste runbook

This is the single place for **all operations that require the user's Windows computer, GitHub account, or physical recording hardware**. Every future user action must be documented here *before* asking the user to execute it. Never depend on chat messages for commands.

## Rules
- Each action includes **when**, **where**, **prerequisites**, **copy/paste command**, **expected output**, and **what to send back**.
- Use PowerShell commands for Windows unless explicitly labeled otherwise.
- Mark actions `PENDING`, `VERIFIED`, `FAILED` or `NOT REQUIRED`; do not claim verification without evidence.
- Commands must not contain real credentials or private host addresses.
- After an action is verified, retain it as a reproducible historical runbook and link its evidence in `STATUS.md`.
- All new user-side checks (CI, actual video recordings, multi-machine tests, EXE smoke tests) go in this document first.

## UA-001 — Verify uv workspace locally

**Status:** PENDING — optional local validation; GitHub Windows CI should do the automated part first.

**Where:** Windows PowerShell with Git and uv installed.

**Prerequisites:** Access to https://github.com/yunfei00/qrft and an internet connection. Install uv from https://docs.astral.sh/uv/getting-started/installation/ if needed.

```powershell
git clone https://github.com/yunfei00/qrft.git
cd qrft
uv python install 3.12
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

**Expected:** uv resolves dependencies, creates a local `.venv`, pytest passes, ruff checks pass. If a command fails, save the complete output rather than retrying blindly.

**Report:** Paste the failing command and its full error output, or report `UA-001 PASS`. Do not send credentials.

## UA-002 — Record real QR video (later stage)

**Status:** NOT REQUIRED YET — encoder not implemented.

When the encoder becomes available, this section will contain the exact executable path, sample file, capture settings, recording steps, and expected hashes. Do not perform this action until the instructions are completed.

## UA-003 — Validate distributed SMB decoding (later stage)

**Status:** NOT REQUIRED YET — decoder/control not implemented.

This section will contain exact PowerShell commands for storage share setup, least-privilege accounts, worker config and two-node validation. Never commit secrets or machine-specific configuration.

## UA-004 — Verify packaged Windows EXEs (later stage)

**Status:** NOT REQUIRED YET — packaging not implemented.

This section will include four EXE paths, launch commands, expected UI/log outputs, and verification steps.
