"""Build the Python FastAPI backend as a Tauri sidecar binary."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "ebook_translator" / "desktop_server.py"
DIST_DIR = ROOT / "build" / "sidecar-dist"
WORK_DIR = ROOT / "build" / "sidecar-work"
SPEC_DIR = ROOT / "build" / "sidecar-spec"
TAURI_BINARIES = ROOT / "frontend" / "src-tauri" / "binaries"
BINARY_NAME = "ebook-translator-backend"


def target_triple() -> str:
    explicit = os.environ.get("TAURI_ENV_TARGET_TRIPLE") or os.environ.get("TARGET")
    if explicit:
        return explicit

    rustc = shutil.which("rustc")
    if rustc:
        proc = subprocess.run(
            [rustc, "-vV"],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("host: "):
                return line.split(":", 1)[1].strip()

    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }.get(machine)
    if not arch:
        raise RuntimeError(
            "Unable to determine target triple. Set TAURI_ENV_TARGET_TRIPLE explicitly."
        )
    if system == "linux":
        return f"{arch}-unknown-linux-gnu"
    if system == "windows":
        return f"{arch}-pc-windows-msvc"
    if system == "darwin":
        return f"{arch}-apple-darwin"
    raise RuntimeError(
        "Unable to determine target triple. Set TAURI_ENV_TARGET_TRIPLE explicitly."
    )


def main() -> None:
    triple = target_triple()
    is_windows = "windows" in triple
    suffix = ".exe" if is_windows else ""

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            BINARY_NAME,
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(WORK_DIR),
            "--specpath",
            str(SPEC_DIR),
            str(ENTRYPOINT),
        ],
        cwd=ROOT,
        check=True,
    )

    built = DIST_DIR / f"{BINARY_NAME}{suffix}"
    if not built.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {built}")

    destination = TAURI_BINARIES / f"{BINARY_NAME}-{triple}{suffix}"
    shutil.copy2(built, destination)
    if not is_windows:
        destination.chmod(destination.stat().st_mode | 0o111)

    print(destination)


if __name__ == "__main__":
    main()
