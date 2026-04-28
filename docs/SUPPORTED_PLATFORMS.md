---
owner: '@inder'
---

# Supported platforms

ai-harness officially supports:

| OS | Status | Notes |
|----|--------|-------|
| **Linux** (Ubuntu 22.04+, Debian, etc.) | ✓ Supported | CI: `ubuntu-latest` × Python 3.11/3.12/3.13 |
| **macOS** (12+) | ✓ Supported | CI: `macos-latest` × Python 3.11/3.12/3.13 |
| **Windows** | ⚠ Best-effort, not officially supported | See below |
| **WSL2** (Windows Subsystem for Linux) | ✓ Supported (counts as Linux) | Recommended for Windows users |

## Python versions

Python 3.11+ is the supported minimum. Python 3.10 is **not supported** — the substrate uses `sys.stdlib_module_names` (3.10+) and several typing features.

CI tests every release on **3.11**, **3.12**, **3.13**. Drop Python versions to a new major release when they go end-of-life upstream.

## Windows policy

Native Windows is best-effort. Specifically:

- **Pre-commit hook** is a bash script. Native Windows cmd or PowerShell will not execute it. WSL2 works.
- **GPG signing** flow assumes OpenSSL/gnupg installed in a Unix-style PATH. Gpg4win works under cmd but the verification scripts may need adjustment.
- **Path handling** in the substrate uses POSIX paths everywhere; Windows checkouts under git for Windows usually work because git auto-converts, but corner cases exist.
- **`make` targets** require GNU make. Most Windows users use `python tools/run_validate.py --fast` directly (B23 fallback in v1.2.1 supports this).
- **CI** does not run on Windows. Bug reports against Windows are welcome but won't block releases.

If you want first-class Windows support, please file an issue describing your use case. We'll consider it once we have ≥3 such requests.

## Architectures

| Arch | Status |
|------|--------|
| x86_64 | ✓ |
| arm64 (Apple Silicon, AWS Graviton) | ✓ |

The substrate is pure-Python; no native binaries ship in any release tag.

## Required tools

The harness gracefully degrades when optional tools are missing — every consumer-facing command emits a `[WARN]` and continues, never silently. See `harness doctor` (Sprint 1+).

| Tool | Status | Used by |
|------|--------|---------|
| `git` | required | `sync_harness`, `init_harness`, every diff-aware check |
| `python3` (3.11+) | required | everything |
| `make` | recommended | inner-loop ergonomics; not required since v1.2.1 (B23 fallback) |
| `gpg` | recommended | tag verification (`sync_harness --trust-key`); install via `brew install gnupg` or distro package |
| `gitleaks` | recommended | `Q13.secret-detected`; check degrades to a `[WARN]` if absent |
| `mypy`, `tsc`, `ruff` | recommended | `Q19.upstream-tool-missing` warns when absent |
| `git-filter-repo` | maintainer-only | `sign_release.sh`, `extract.sh` |

## Revision history

- **2026-04-29** (this file) — initial publication; declares the matrix as part of Sprint 0 / S0.6.
