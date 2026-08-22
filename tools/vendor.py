#!/usr/bin/env python3
"""Copy the standard's shared/ tree into a consumer project and write its lock.

    tools/vendor.py <consumer-repo-path>

Files are physically committed into the consumer. There is deliberately no submodule, no runtime
fetch and no cross-repo package: an old tag of a consumer must still build and release offline,
years later, with this repository unreachable. That property is the whole reason this design is
safe, and it is worth more than any convenience a live dependency would buy.

`packaging/project.env` is the consumer's own parameter file and is never vendored or locked.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SHARED = HERE / "shared"
LOCK_NAME = "STANDARD.lock"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shared_files() -> list[Path]:
    """Every file the standard vendors, in a stable order.

    `__pycache__` is excluded because running any of these scripts once creates it, and a bare
    rglob then vendored the bytecode: the lock recorded a hash that changes with the interpreter
    that happened to compile it, so a consumer's sync check would fail for a reason that has
    nothing to do with the standard.
    """
    return sorted(
        p
        for p in SHARED.rglob("*")
        if p.is_file()
        and p.name != "project.env.example"
        and p.suffix != ".pyc"
        and "__pycache__" not in p.parts
    )


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    consumer = Path(sys.argv[1]).resolve()
    if not consumer.is_dir():
        print(f"not a directory: {consumer}", file=sys.stderr)
        return 2

    files: dict[str, str] = {}
    for src in shared_files():
        rel = src.relative_to(SHARED)
        dst = consumer / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files[str(rel)] = digest(src)
        print(f"  vendored {rel}")

    lock = {
        "source_repo": "SisyphusMD/project-standard",
        "source_tag": git("describe", "--tags", "--exact-match") or "(untagged working tree)",
        "source_commit": git("rev-parse", "HEAD") or "(no commit)",
        "files": dict(sorted(files.items())),
    }
    (consumer / LOCK_NAME).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"  wrote {LOCK_NAME} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
