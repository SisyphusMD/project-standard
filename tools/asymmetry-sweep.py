#!/usr/bin/env python3
"""Every structural difference between two sibling repos, found mechanically.

    asymmetry-sweep.py ../whiskerless ../dreame-valetudo

`capability-diff.py` answers "does each project have the things we thought to ask about". It has
three blind spots, and one of them has already cost real gaps: it cannot see a capability NEITHER
project has, it only measures what someone remembered to write a probe for, and it asks whether a
thing exists rather than whether it is equally good.

This closes the second one from the other end. It asks no questions at all — it enumerates what is
THERE, on both sides, and prints every difference. Most output is noise that needs one sentence of
triage; the point is that nothing can hide in it by never having been asked about.

Project names are normalised away, so `src/whiskerless/cli.py` and `src/dreame_valetudo/cli.py`
are the same entry, and only genuine structural differences survive.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: Everything that differs between the two only because they are different projects.
_NOISE = re.compile(
    r"whiskerless|whisker|dreame[-_]valetudo|dreame|litter[-_]robot_?4?|litterrobot|lr4|sisyphusmd",
    re.I,
)

#: Not structure: generated, vendored-in-place, or private working notes.
_SKIP = re.compile(r"^(\.git/|\.venv|.*/__pycache__/|\.claude/|node_modules/)")


def _tracked(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return [p for p in out if not _SKIP.match(p)]


def _norm(path: str) -> str:
    """A path with the project's own name removed, so the two are comparable."""
    return _NOISE.sub("<project>", path)


def _shape(repo: Path) -> dict[str, set[str]]:
    files = _tracked(repo)
    shape: dict[str, set[str]] = {
        "workflow files": set(),
        "packaging scripts": set(),
        "test files": set(),
        "documentation": set(),
        "source modules": set(),
        "top-level files": set(),
    }
    for f in files:
        n = _norm(f)
        if "/workflows/" in f:
            shape["workflow files"].add(n)
        elif f.startswith("packaging/"):
            shape["packaging scripts"].add(n)
        elif f.startswith("tests/"):
            shape["test files"].add(n)
        elif f.startswith("docs/"):
            shape["documentation"].add(n)
        elif f.endswith(".py") and (f.startswith("src/") or f.startswith("custom_components/")):
            shape["source modules"].add(n)
        elif "/" not in f:
            shape["top-level files"].add(n)
    shape["workflow jobs"] = _jobs(repo, files)
    shape["CLI verbs"] = _verbs(repo, files)
    return shape


def _jobs(repo: Path, files: list[str]) -> set[str]:
    """Job names, read as text rather than parsed: this must not need a YAML library, and a job
    name is a top-level two-space key under `jobs:` in every workflow either project writes."""
    found: set[str] = set()
    for f in files:
        if "/workflows/" not in f or not f.endswith((".yml", ".yaml")):
            continue
        text = (repo / f).read_text(errors="replace")
        if "\njobs:\n" not in text:
            continue
        body = text.split("\njobs:\n", 1)[1]
        for line in body.splitlines():
            if re.fullmatch(r"  [a-zA-Z0-9_-]+:", line.rstrip()):
                found.add(f"{_norm(f)} :: {line.strip().rstrip(':')}")
    return found


def _verbs(repo: Path, files: list[str]) -> set[str]:
    """Subcommands, however each CLI spells its registration."""
    found: set[str] = set()
    for f in files:
        if not f.endswith("cli.py"):
            continue
        text = (repo / f).read_text(errors="replace")
        found |= set(re.findall(r'add_parser\(\s*"([a-z][a-z0-9-]*)"', text))
        found |= set(re.findall(r'cmd == "([a-z][a-z0-9-]*)"', text))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--dimension", help="only this dimension")
    args = ap.parse_args()

    shape_a, shape_b = _shape(args.a), _shape(args.b)
    name_a, name_b = args.a.resolve().name, args.b.resolve().name

    total = 0
    for dimension in sorted(shape_a):
        if args.dimension and args.dimension != dimension:
            continue
        only_a = sorted(shape_a[dimension] - shape_b[dimension])
        only_b = sorted(shape_b[dimension] - shape_a[dimension])
        if not only_a and not only_b:
            print(f"== {dimension}: symmetric ({len(shape_a[dimension])} each)")
            continue
        shared = len(shape_a[dimension] & shape_b[dimension])
        print(f"== {dimension}: {len(only_a) + len(only_b)} asymmetric, {shared} shared")
        for item in only_a:
            print(f"   {name_a:>16} only   {item}")
        for item in only_b:
            print(f"   {name_b:>16} only   {item}")
        total += len(only_a) + len(only_b)
    print(f"\n{total} asymmetries. Each is a question to answer, not a defect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
