# Windows Release Environment

Windows is the authoritative environment for Ebook Translator desktop release verification.

Linux remains supported for backend/frontend development and automated tests, but Linux Tauri packaging is not a v1.0 release gate.

## Target

Primary target:

```text
x86_64-pc-windows-msvc
Windows 10/11
Tauri v2
NSIS installer first
MSI optional after NSIS passes
```

## Required Windows prerequisites

Install before running the release script:

1. Node.js 22 or 24 stable (LTS/stable release, not alpha/nightly).
2. Python 3.12+.
3. Rust via rustup with the stable MSVC host toolchain.
4. Microsoft C++ Build Tools with **Desktop development with C++** selected.
5. Microsoft Edge WebView2 Runtime. Windows 10 1803+ and Windows 11 normally already include it.

For MSI builds, Windows VBSCRIPT support may also be required. The first v1.0 verification target is NSIS to avoid making MSI-specific tooling a blocker.

## One-command release build

From PowerShell at the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows_release.ps1
```

The script verifies the runtime/toolchain, creates a local `.release-venv`, installs build dependencies, runs backend tests, installs frontend dependencies, builds the frontend, builds the Python sidecar, runs `cargo check --locked`, then produces an NSIS installer with Tauri.

## Expected gates

The script must complete all of these:

```text
Node 22/24 stable
Rust MSVC host toolchain
Python build environment
pytest PASS
npm ci PASS
npm run build PASS
Windows sidecar .exe generated
cargo check --locked PASS
Tauri NSIS bundle PASS
```

Expected sidecar path for x64 Windows:

```text
frontend/src-tauri/binaries/ebook-translator-backend-x86_64-pc-windows-msvc.exe
```

Generated sidecar binaries remain ignored by Git.

## Gate 4 packaged smoke test

Do not tag `v1.0-rc1` immediately after the installer builds. Install the generated NSIS package on a clean Windows 10/11 machine or clean Windows VM and verify:

```text
1. Installer completes.
2. App launches without a console window dependency.
3. Python sidecar starts automatically.
4. Frontend reaches backend readiness without manual restart.
5. Import an EPUB and a TXT file.
6. Run a small Standard translation using Ollama or a controlled provider.
7. Inspect QA results and edit one translated chunk.
8. Save one correction to Translation Memory.
9. Export TXT and EPUB.
10. Close the application.
11. Confirm the sidecar process exits.
12. Relaunch and confirm persisted books/jobs remain available.
13. Interrupt a translation, relaunch, and resume the same persisted job.
14. Confirm completed chunks are not translated again.
15. Confirm exported EPUB reopens with assets/TOC intact.
```

## Release evidence

Record at minimum:

```text
Windows edition/build
CPU architecture
node --version
npm --version
rustc --version
cargo --version
python --version
pytest result
npm build result
cargo check result
installer filename/hash
install/launch/relaunch/resume/export smoke result
```

Keep credentials out of release logs. API keys are session-only and must never be stored in the repository or release evidence.

## MSI later

After NSIS passes, MSI may be verified separately. Tauri's Windows installer documentation notes that MSI builds use WiX and may require the Windows VBSCRIPT optional feature. MSI is not required to unblock the first release candidate.
