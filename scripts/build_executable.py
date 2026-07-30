#!/usr/bin/env python3
"""Build and verify a standalone PDF Add Numbers executable."""

from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
ENTRY_POINT: Final[Path] = PROJECT_ROOT / "src" / "pdf_add_nmbrs" / "cli.py"
BINARY_NAME: Final[str] = "pdf-add-nmbrs"


class ExecutableBuildError(Exception):
    """Raised when the standalone executable cannot be built or verified."""


def platform_tag() -> str:
    """Return a stable distribution directory name for the current platform."""
    system = platform.system().lower()
    systems = {
        "darwin": "macos",
        "linux": "linux",
        "windows": "windows",
    }
    if system not in systems:
        raise ExecutableBuildError(f"unsupported operating system: {system}")
    machine = platform.machine().lower()
    architectures = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return f"{systems[system]}-{architectures.get(machine, machine or 'unknown')}"


def executable_filename() -> str:
    """Return the executable filename for the current platform."""
    suffix = ".exe" if platform.system().lower() == "windows" else ""
    return f"{BINARY_NAME}{suffix}"


def sha256(path: Path) -> str:
    """Return the SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(
    *,
    output_directory: Path,
    work_directory: Path,
    clean: bool = True,
) -> Path:
    """Build the one-file executable and run a help smoke test."""
    output_directory = output_directory.expanduser().resolve()
    work_directory = work_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    (work_directory / "specs").mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name",
        BINARY_NAME,
        "--distpath",
        str(output_directory),
        "--workpath",
        str(work_directory / BINARY_NAME),
        "--specpath",
        str(work_directory / "specs"),
        "--paths",
        str(PROJECT_ROOT / "src"),
        "--collect-all",
        "pdfplumber",
        "--collect-all",
        "pypdf",
        "--collect-all",
        "reportlab",
    ]
    if clean:
        command.append("--clean")
    command.append(str(ENTRY_POINT))

    process = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if process.returncode != 0:
        raise ExecutableBuildError(
            f"PyInstaller failed with exit code {process.returncode}"
        )

    executable = output_directory / executable_filename()
    if not executable.is_file():
        raise ExecutableBuildError(f"expected executable was not created: {executable}")

    smoke_test = subprocess.run(
        [str(executable), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if smoke_test.returncode != 0:
        detail = smoke_test.stderr.strip() or smoke_test.stdout.strip()
        raise ExecutableBuildError(f"executable smoke test failed: {detail}")

    checksum_path = output_directory / "SHA256SUMS.txt"
    checksum_path.write_text(
        f"{sha256(executable)}  {executable.name}\n",
        encoding="utf-8",
    )
    return executable


def create_parser() -> argparse.ArgumentParser:
    """Create the build command parser."""
    tag = platform_tag()
    parser = argparse.ArgumentParser(
        description="Build a standalone PDF Add Numbers executable."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "dist" / "executables" / tag,
        help="Directory receiving the executable and SHA256SUMS.txt.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=PROJECT_ROOT / "build" / "pyinstaller" / tag,
        help="Directory for temporary PyInstaller files.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Reuse PyInstaller caches.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build the executable."""
    try:
        args = create_parser().parse_args(argv)
        executable = build(
            output_directory=args.output_dir,
            work_directory=args.work_dir,
            clean=not args.no_clean,
        )
    except (ExecutableBuildError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Built: {executable}")
    print(f"Checksums: {executable.parent / 'SHA256SUMS.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

