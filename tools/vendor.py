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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent.parent
SHARED = HERE / "shared"
LOCK_NAME = "STANDARD.lock"
HEX64 = re.compile(r"[0-9a-f]{64}")


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


def any_symlink_on_the_way(consumer: Path, rel: str) -> bool:
    """True if any component of `rel`, the last one included, is a symlink."""
    cursor = consumer
    for part in Path(rel).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def replace_in_place(src: Path, dst: Path) -> None:
    """Copy `src` over `dst` without ever truncating the file `dst` names.

    Vendoring routinely overwrites scripts that are running at that moment — `refresh-pins.sh`
    invokes the re-vendor, and the standard can ship a new copy of both. A plain copy truncates and
    rewrites the same inode, and bash reads a script incrementally by file offset: the interpreter
    resumes at a byte position that now points into different text. Renaming a finished file over
    the name leaves the running inode untouched, so the shell in flight sees the version it started
    with and the new one takes effect on the next run.
    """
    with tempfile.NamedTemporaryFile(
        dir=dst.parent, prefix=f".{dst.name}.", suffix=".vendor-tmp", delete=False
    ) as staged:
        # Created exclusively rather than at a name that can be guessed: a predictable sibling may
        # already exist as a consumer's file, or as a symlink whose target would be written instead.
        tmp = Path(staged.name)
        staged.write(src.read_bytes())
    try:
        shutil.copystat(src, tmp)
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)


def manifest(consumer: Path) -> dict[str, str]:
    """What the consumer's lock says it already holds, or nothing at all for a fresh consumer.

    Every entry is checked, not just the shape around them. A digest that is not a sha256 can never
    match the file it names, so a retired path carrying one would be read as "edited here", kept,
    and then dropped from the new lock: stale on disk and invisible to the drift check.
    """
    lock_path = consumer / LOCK_NAME
    if not lock_path.is_file():
        return {}  # a first vendoring into a fresh consumer owns nothing yet
    try:
        previous = json.loads(lock_path.read_text())["files"]
        if not isinstance(previous, dict):
            raise TypeError(f"'files' is {type(previous).__name__}, not an object")
        for key, value in previous.items():
            if not isinstance(key, str) or not isinstance(value, str) or not HEX64.fullmatch(value):
                raise TypeError(f"entry {key!r} does not map a path to a sha256")
            # Canonical and relative, or two spellings can name one file: both enter the retirement
            # list, and the second unlink fails after the first already deleted it, leaving the old
            # lock in place describing content that is gone.
            spelled = PurePosixPath(key)
            if spelled.is_absolute() or ".." in spelled.parts or str(spelled) != key:
                raise TypeError(f"entry {key!r} is not a canonical relative path")
    except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        # Not recoverable by carrying on. Treating an unreadable lock as "nothing was vendored"
        # would overwrite the only record of what this consumer holds, stranding every retired
        # file on disk and outside the new lock, where the drift check cannot see it.
        raise SystemExit(
            f"{lock_path} exists but cannot be read ({exc}); refusing to vendor over it"
        ) from exc
    return previous


def retired(consumer: Path, previous: dict[str, str], current: dict[str, str]) -> list[str]:
    """Paths the previous lock owned that this version of the standard no longer ships.

    Copying alone makes a rename additive: the new name arrives, the old one stays, and because the
    fresh lock simply stops mentioning it the drift check reports green over a file nobody meant to
    keep. The consumer then carries a script the standard has already replaced, and the next reader
    cannot tell which of the two is live.

    A path is only removed when its bytes still match what the old lock recorded. Anything edited
    in the consumer is left alone and announced instead: the standard has no claim on content it
    did not write, and a silent delete of someone's local change is worse than an orphan.
    """
    root = consumer.resolve()
    gone = []
    for rel, was in sorted(previous.items()):
        if rel in current:
            continue
        path = consumer / rel
        # Deletion driven by file contents. An absolute or `..` entry, or a path that leaves the
        # tree through a symlink, would otherwise unlink something this tool has no business
        # touching, so containment is checked against the resolved location, not the spelling.
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except (ValueError, OSError):
            print(f"  REFUSED {rel}: lock entry resolves outside the consumer", file=sys.stderr)
            continue
        # Containment of the endpoint is not containment of the walk. A symlinked component can
        # land inside the consumer and still mean the unlink removes a file the standard never
        # placed there, so the route is checked as well as the destination.
        if any_symlink_on_the_way(consumer, rel):
            print(f"  REFUSED {rel}: reached through a symlink", file=sys.stderr)
            continue
        if not path.exists() and not path.is_symlink():
            continue  # already gone; nothing to retire
        if not path.is_file():
            # Something else now occupies a path the standard used to own. Dropping it from the
            # lock without a word is what leaves an orphan no drift check will ever mention.
            print(f"  KEPT {rel}: no longer part of the standard, and not a file here", file=sys.stderr)
            continue
        if digest(path) != was:
            print(f"  KEPT {rel}: no longer part of the standard, but edited here", file=sys.stderr)
            continue
        gone.append(rel)
    return gone


def survivors_under(path: Path, doomed: set[Path]) -> list[Path]:
    """Everything beneath `path` that this run will not remove.

    Not just regular files. A dangling symlink, a fifo or an empty directory nobody tracked all
    keep a directory alive just as effectively, and `is_file()` sees none of them. An empty
    directory counts because nothing retires it: pruning only visits the ancestors of deleted
    files, so a directory that never held one is never even looked at.
    """
    if path.is_dir() and not path.is_symlink():
        children = sorted(path.iterdir())
        if not children:
            return [path]
        return [x for child in children for x in survivors_under(child, doomed)]
    return [] if path in doomed else [path]


def obstructions(consumer: Path, sources: list[Path], removed: list[str]) -> list[str]:
    """Paths where a shipped file cannot land because consumer-owned content holds the name.

    Checked before anything is deleted rather than at the copy itself. Retirement and copying are
    one operation from the consumer's point of view: aborting halfway leaves files gone, the lock
    still naming them, and no single command to get back to either side of the change.

    A directory whose every file is on its way out is not an obstruction — pruning will clear it.
    """
    doomed = {consumer / rel for rel in removed}
    blocked = []
    for src in sources:
        rel = src.relative_to(SHARED)
        dst = consumer / rel

        # A file cannot be written beneath something that is not a directory, and an ancestor kept
        # back by retirement stays exactly that. Left to the copy, this surfaces as a bare
        # FileExistsError after earlier files have already been written.
        ancestor = dst.parent
        while ancestor != consumer and consumer in ancestor.parents:
            if ancestor.exists() and not ancestor.is_dir() and ancestor not in doomed:
                blocked.append(f"{rel} (blocked by the file at {ancestor.relative_to(consumer)})")
                break
            ancestor = ancestor.parent

        if dst.is_dir() and not dst.is_symlink():
            survivors = survivors_under(dst, doomed)
            if survivors:
                names = ", ".join(sorted(str(x.relative_to(dst)) or "." for x in survivors))
                blocked.append(f"{rel} (holds {names})")
    return blocked


def prune_empty_dirs(consumer: Path, removed: list[str]) -> None:
    """Drop directories a retirement emptied, walking up from each deleted file.

    Only the ancestors of paths this run deleted are considered. A sweep of the whole consumer
    would be a far larger promise than retiring a file: it would reach directories the standard
    never owned, and the repository's own `.git` is full of them.
    """
    for rel in removed:
        parent = (consumer / rel).parent
        while parent != consumer and consumer in parent.parents:
            if not parent.is_dir() or any(parent.iterdir()):
                break
            parent.rmdir()
            print(f"  removed empty {parent.relative_to(consumer)}")
            parent = parent.parent


def git(*args: str) -> str | None:
    """Command output, or None when git could not answer at all.

    The distinction matters for `status --porcelain`, where silence is the answer meaning "clean".
    Flattening a failed call into that same empty string reports a dirty or unreadable tree as a
    clean one, and the stamp it produces is exactly the lie the dirty check exists to prevent.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def source_tag() -> str:
    """What the vendored bytes actually came from, which is not always what HEAD is tagged.

    `git describe --exact-match` reports the tag on a dirty tree just as happily as on a clean one,
    so vendoring mid-edit stamps a lock with a tag whose content it does not hold. Everything
    downstream then treats that claim as settled: the sync check certifies the files, and the
    re-vendor sees a matching tag and skips the fetch that would have corrected it. Naming the
    dirt keeps the lie from being expressible.
    """
    tag = git("describe", "--tags", "--exact-match")
    if not tag:
        return "(untagged working tree)"
    status = git("status", "--porcelain")
    clean = status == ""  # None means git could not tell us, which is not the same as clean
    return tag if clean else f"{tag} (dirty working tree)"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    consumer = Path(sys.argv[1]).resolve()
    if not consumer.is_dir():
        print(f"not a directory: {consumer}", file=sys.stderr)
        return 2

    sources = shared_files()
    files = {str(src.relative_to(SHARED)): digest(src) for src in sources}

    # Retirement runs first. A path that turned from a file into a directory upstream still has the
    # old object sitting in the way here, and the copy below would fail on it before anything got
    # the chance to clear it.
    previous_manifest = manifest(consumer)
    removed = retired(consumer, previous_manifest, files)

    blocked = obstructions(consumer, sources, removed)
    if blocked:
        raise SystemExit(
            "cannot vendor: a directory occupies a path the standard ships as a file, and holds "
            "content the standard did not put there. Resolve by hand, then re-run:\n  "
            + "\n  ".join(blocked)
        )

    for rel in removed:
        (consumer / rel).unlink()
        print(f"  retired {rel}")
    prune_empty_dirs(consumer, removed)

    for src in sources:
        rel = src.relative_to(SHARED)
        dst = consumer / rel
        if dst.is_dir() and not dst.is_symlink():
            # The reverse rename: upstream turned a directory into a file, but the directory here
            # still holds something the consumer added, so pruning rightly left it. Copying now
            # would drop the file *inside* it and lock a hash against a path that is not a file,
            # which reads as success and fails the very next sync check. A symlink pointing at a
            # directory is not this case: the rename below replaces the link itself, which is both
            # what the preflight assumed and the only outcome that leaves the target alone.
            raise SystemExit(
                f"cannot vendor {rel}: a directory occupies that path and is not empty "
                f"({', '.join(sorted(c.name for c in dst.iterdir()))}); resolve it by hand"
            )
        adopted = dst.is_file() and str(rel) not in previous_manifest
        dst.parent.mkdir(parents=True, exist_ok=True)
        replace_in_place(src, dst)
        if adopted:
            # The standard has started shipping a path the consumer already filled. Overwriting is
            # the right outcome — that is what adopting a shared file means — but it must not be
            # the quiet one, now that a Renovate bump can perform it with nobody watching.
            print(f"  ADOPTED {rel}: replaced a file the standard did not previously own",
                  file=sys.stderr)
        else:
            print(f"  vendored {rel}")

    lock = {
        "source_repo": "SisyphusMD/project-standard",
        "source_tag": source_tag(),
        "source_commit": git("rev-parse", "HEAD") or "(no commit)",
        "files": dict(sorted(files.items())),
    }
    (consumer / LOCK_NAME).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"  wrote {LOCK_NAME} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
