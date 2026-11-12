"""Builds the backend into a single self-contained executable for the Tauri bundle.

    uv run python scripts/build_sidecar.py

Output: desktop/src-tauri/binaries/localledger-backend-<rust target triple>, the naming
Tauri's `externalBin` expects. End users then need no Python installation.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND.parent / "desktop" / "src-tauri" / "binaries"
TRIPLES = {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}


def main() -> None:
    if sys.platform != "darwin":
        sys.exit("The sidecar build currently supports macOS only.")
    triple = TRIPLES[platform.machine()]
    with tempfile.TemporaryDirectory() as work:
        subprocess.run(  # noqa: S603 - fixed argument list, no user input
            [
                sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
                "--name", "localledger-backend",
                "--distpath", f"{work}/dist", "--workpath", f"{work}/build",
                "--specpath", work,
                "--collect-submodules", "uvicorn",
                "--collect-submodules", "keyring",
                "--collect-all", "sqlcipher3",
                "--paths", str(BACKEND),
                str(BACKEND / "scripts" / "sidecar_entry.py"),
            ],
            check=True,
        )
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUT_DIR / f"localledger-backend-{triple}"
        shutil.copy2(Path(work) / "dist" / "localledger-backend", target)
        target.chmod(0o755)
    print(f"Built {target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
