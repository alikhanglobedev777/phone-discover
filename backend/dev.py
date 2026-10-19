"""One-command native Windows Django launcher: `py dev.py` (or `python dev.py`).

Uses this repository's existing scripts/setup-backend-native.ps1 and
scripts/run-backend-native.ps1. These handle local .env files, PostgreSQL,
Redis, migrations, and Django without npm or manual venv activation.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
VENV_PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
REQUIREMENTS = BACKEND / "requirements.txt"
STAMP = BACKEND / ".venv" / "requirements.sha256"
SETUP_SCRIPT = ROOT / "scripts" / "setup-backend-native.ps1"
RUN_SCRIPT = ROOT / "scripts" / "run-backend-native.ps1"


def run_powershell(executable: str, script: Path, *, no_docker: bool) -> int:
    command = [
        executable,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    if no_docker:
        command.append("-SkipInfrastructure")
    return subprocess.call(command, cwd=ROOT)


def needs_setup(digest: str) -> bool:
    if (
        not VENV_PYTHON.is_file()
        or not (BACKEND / ".env.local").is_file()
        or not (ROOT / ".env").is_file()
    ):
        return True
    try:
        if STAMP.read_text(encoding="utf-8").strip() != digest:
            return True
    except OSError:
        return True

    # Avoid a confusing traceback if someone has removed packages from the venv.
    try:
        result = subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                "import django, rest_framework, corsheaders, django_filters, psycopg, dj_database_url, dotenv",
            ],
            cwd=BACKEND,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode != 0
    except OSError:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Phone Discover Django backend")
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Do not start Docker (requires PostgreSQL and Redis already running)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Reinstall/refresh backend dependencies before starting",
    )
    args = parser.parse_args()

    if os.name != "nt":
        parser.error("This launcher uses the repository's Windows PowerShell scripts.")

    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell:
        parser.error("PowerShell was not found. Start this command from Windows PowerShell.")
    if not (SETUP_SCRIPT.is_file() and RUN_SCRIPT.is_file() and REQUIREMENTS.is_file()):
        parser.error("Missing backend requirements or native setup scripts.")

    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest().upper()
    try:
        if args.setup or needs_setup(digest):
            print("Preparing Django environment (first run may take a few minutes)...", flush=True)
            result = run_powershell(powershell, SETUP_SCRIPT, no_docker=args.no_docker)
            if result:
                return result
            # Write only when the setup, system checks, and migrations all succeeded.
            STAMP.write_text(digest + "\n", encoding="utf-8")

        print("Starting Django at http://127.0.0.1:8000/", flush=True)
        return run_powershell(powershell, RUN_SCRIPT, no_docker=args.no_docker)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Backend startup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
