"""Vendoring is a two-way operation: it copies what the standard has, and drops what it lost."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "tools" / "vendor.py"


def vendor(consumer: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VENDOR), str(consumer)], capture_output=True, text=True, check=True
    )


def locked(consumer: Path) -> dict[str, str]:
    return json.loads((consumer / "STANDARD.lock").read_text())["files"]


def test_a_file_the_standard_stops_shipping_does_not_live_on_in_the_consumer(
    tmp_path: Path,
) -> None:
    """Copying alone makes every rename additive.

    The new name arrives, the old one stays, and the fresh lock simply stops mentioning it — so the
    drift check reports green over a script the standard already replaced. A reader then finds two
    plausible copies with no way to tell which one is live.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    orphan = "packaging/retired-by-the-standard.sh"
    (consumer / orphan).write_text("#!/usr/bin/env bash\n")
    lock_path = consumer / "STANDARD.lock"
    lock = json.loads(lock_path.read_text())
    lock["files"][orphan] = hashlib.sha256((consumer / orphan).read_bytes()).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    vendor(consumer)

    assert not (consumer / orphan).exists(), "the standard stopped shipping it; it is still here"
    assert orphan not in locked(consumer)


def test_vendoring_never_silently_deletes_something_the_consumer_edited(tmp_path: Path) -> None:
    """The standard has no claim on content it did not write.

    A path can be retired upstream and meanwhile be carrying a local change. Deleting that on the
    consumer's behalf destroys work no one asked to lose, so an unrecognised file is announced and
    left in place instead.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    orphan = "packaging/edited-here.sh"
    lock_path = consumer / "STANDARD.lock"
    lock = json.loads(lock_path.read_text())
    lock["files"][orphan] = "0" * 64  # a hash the file on disk will not match
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    (consumer / orphan).write_text("# a local change\n")

    result = vendor(consumer)

    assert (consumer / orphan).read_text() == "# a local change\n"
    assert "edited here" in result.stderr, f"the refusal was silent: {result.stderr!r}"


def test_retiring_the_last_file_in_a_directory_takes_the_directory_too(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    nested = "tests/release/gone/only-file.sh"
    (consumer / "tests" / "release" / "gone").mkdir(parents=True)
    (consumer / nested).write_text("#!/usr/bin/env bash\n")
    lock_path = consumer / "STANDARD.lock"
    lock = json.loads(lock_path.read_text())
    lock["files"][nested] = hashlib.sha256((consumer / nested).read_bytes()).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    vendor(consumer)

    assert not (consumer / "tests" / "release" / "gone").exists()
    assert (consumer / "tests" / "release").is_dir(), "pruning climbed past what it emptied"


def test_a_lock_entry_cannot_reach_outside_the_consumer(tmp_path: Path) -> None:
    """Retirement deletes paths named by a file, which makes containment a safety property."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    bystander = tmp_path / "not-ours.txt"
    bystander.write_text("untouched\n")
    vendor(consumer)

    lock_path = consumer / "STANDARD.lock"
    for escape in ("../not-ours.txt", "/etc/passwd", "./packaging/x.sh"):
        lock = json.loads(lock_path.read_text())
        lock["files"][escape] = hashlib.sha256(bystander.read_bytes()).hexdigest()
        text = json.dumps(lock, indent=2, sort_keys=True) + "\n"
        lock_path.write_text(text)

        result = subprocess.run(
            [sys.executable, str(VENDOR), str(consumer)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode != 0, f"accepted a lock entry spelled {escape!r}"
        assert bystander.exists(), "vendoring deleted a file outside the consumer"
        assert lock_path.read_text() == text, "rewrote the lock it had just rejected"
        lock_path.write_text(json.dumps({**lock, "files": {
            k: v for k, v in lock["files"].items() if k != escape}}, indent=2, sort_keys=True) + "\n")


def test_an_unreadable_lock_stops_vendoring_instead_of_being_overwritten(tmp_path: Path) -> None:
    """The lock is the only record of what the consumer holds.

    Treating a corrupt one as "nothing is vendored here" would rewrite it from scratch, stranding
    every file the standard has since retired: present on disk, absent from the lock, invisible to
    the drift check that is supposed to notice exactly that.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)
    (consumer / "STANDARD.lock").write_text("{ this is not json\n")

    result = subprocess.run(
        [sys.executable, str(VENDOR), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0, "vendored straight over a lock it could not read"
    assert "refusing" in result.stderr.lower()
    assert (consumer / "STANDARD.lock").read_text() == "{ this is not json\n"


def build_standard(root: Path, layout: dict[str, str]) -> Path:
    """A miniature standard whose shared/ tree the caller controls exactly.

    The real one cannot express "this path used to be a file and is now a directory" from inside a
    test, and that is precisely the shape being checked.
    """
    (root / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(VENDOR, root / "tools" / "vendor.py")
    shared = root / "shared"
    if shared.exists():
        shutil.rmtree(shared)
    for rel, body in layout.items():
        dst = shared / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body)
    return root / "tools" / "vendor.py"


def test_a_path_that_became_a_directory_upstream_can_still_be_vendored(tmp_path: Path) -> None:
    """Copying before retiring makes topology changes unrepresentable.

    The retired file still occupies the name the new directory needs, so `mkdir` raises and the
    rename can never land — and a rename is the likeliest thing to arrive with a standard bump.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/helper.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    assert (consumer / "packaging" / "helper.sh").is_file()

    tool = build_standard(standard, {"packaging/helper.sh/main.sh": "#!/usr/bin/env bash\n"})
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, f"the rename could not be vendored: {result.stderr}"
    assert (consumer / "packaging" / "helper.sh").is_dir()
    assert (consumer / "packaging" / "helper.sh" / "main.sh").is_file()


def test_a_lock_without_a_files_map_is_malformed_not_empty(tmp_path: Path) -> None:
    """Valid JSON is not a valid lock.

    `.get("files", {})` reads a lock missing its manifest as a fresh consumer that owns nothing,
    so vendoring overwrites it and every retired file stays on disk outside the new lock — the
    same blind spot as an unparseable one, reached through a file that parses fine.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    for broken in (
        '{"source_repo": "x"}',
        '{"files": []}',
        '{"files": "nope"}',
        '{"files": {"packaging/x.sh": "not-a-digest"}}',
        '{"files": {"packaging/x.sh": null}}',
        '{"files": {"packaging/x.sh": "ABCDEF"}}',
    ):
        (consumer / "STANDARD.lock").write_text(broken + "\n")
        result = subprocess.run(
            [sys.executable, str(VENDOR), str(consumer)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, f"vendored over a lock with no manifest: {broken}"
        assert (consumer / "STANDARD.lock").read_text() == broken + "\n"


def test_a_directory_in_the_way_of_a_shipped_file_stops_the_vendor(tmp_path: Path) -> None:
    """The reverse rename, where the consumer's own files keep the old directory alive.

    `shutil.copy2` onto a directory writes the file inside it and returns happily. The lock then
    records that path as a file, the vendor reports success, and the sync check fails on the next
    run with nothing to explain why.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/thing/inner.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    (consumer / "packaging" / "thing" / "local-note.txt").write_text("mine\n")

    tool = build_standard(standard, {"packaging/thing": "#!/usr/bin/env bash\n"})
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0, "copied a file into the directory blocking its path"
    assert (consumer / "packaging" / "thing").is_dir()
    assert (consumer / "packaging" / "thing" / "local-note.txt").exists()
    assert "local-note.txt" in result.stderr, f"did not name the obstruction: {result.stderr!r}"
    # Refusing halfway is its own failure: the consumer would be left with files deleted, the lock
    # still naming them, and no single command that returns it to either side of the change.
    assert (consumer / "packaging" / "thing" / "inner.sh").exists(), (
        "aborted after already retiring a locked file"
    )
    assert json.loads((consumer / "STANDARD.lock").read_text())["files"], "lock was rewritten"


def test_retirement_does_not_follow_a_symlink_to_reach_its_target(tmp_path: Path) -> None:
    """Containment of the endpoint is not containment of the walk.

    A symlinked component can resolve to somewhere legitimately inside the consumer while still
    meaning the unlink removes a file the standard never put there.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    real = consumer / "elsewhere" / "precious.sh"
    real.parent.mkdir()
    real.write_text("#!/usr/bin/env bash\n")
    (consumer / "packaging" / "link").symlink_to(real)

    lock_path = consumer / "STANDARD.lock"
    lock = json.loads(lock_path.read_text())
    lock["files"]["packaging/link"] = hashlib.sha256(real.read_bytes()).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    result = vendor(consumer)

    assert real.exists(), "unlink followed a symlink out of the path it was given"
    assert "REFUSED" in result.stderr


def test_a_retired_path_replaced_by_a_directory_is_announced(tmp_path: Path) -> None:
    """Silence here recreates the orphan the retirement was added to prevent."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    vendor(consumer)

    taken = "packaging/now-a-dir"
    (consumer / taken).mkdir()
    (consumer / taken / "local.txt").write_text("mine\n")
    lock_path = consumer / "STANDARD.lock"
    lock = json.loads(lock_path.read_text())
    lock["files"][taken] = "a" * 64
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    result = vendor(consumer)

    assert (consumer / taken).is_dir()
    assert "not a file here" in result.stderr, f"dropped it silently: {result.stderr!r}"


def test_vendoring_from_a_dirty_tree_does_not_stamp_a_clean_tag(tmp_path: Path) -> None:
    """`git describe --exact-match` reports the tag on a dirty tree exactly as on a clean one.

    A lock stamped that way claims content the tag never had, and everything downstream believes
    it: the sync check certifies the files, and the re-vendor sees a matching tag and skips the
    fetch that would have corrected them.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    tool = build_standard(standard, {"packaging/helper.sh": "#!/usr/bin/env bash\n"})

    def run_git(*args: str) -> None:
        subprocess.run(["git", "-C", str(standard), *args], capture_output=True, check=True)

    run_git("init", "-q")
    run_git("config", "user.email", "t@example.invalid")
    run_git("config", "user.name", "t")
    run_git("add", "-A")
    run_git("commit", "-qm", "initial")
    run_git("tag", "v9.9.9")

    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    assert json.loads((consumer / "STANDARD.lock").read_text())["source_tag"] == "v9.9.9"

    (standard / "shared" / "packaging" / "helper.sh").write_text("#!/usr/bin/env bash\n# edited\n")
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    stamped = json.loads((consumer / "STANDARD.lock").read_text())["source_tag"]
    assert stamped != "v9.9.9", "a dirty tree was stamped as the clean tag"
    assert "dirty" in stamped


def test_pruning_reaches_a_parent_emptied_by_its_own_children(tmp_path: Path) -> None:
    """A parent judged while a child still occupied it must be judged again once the child goes."""
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(
        standard,
        {"packaging/group/nested/deep.sh": "#!/usr/bin/env bash\n",
         "packaging/group/flat.sh": "#!/usr/bin/env bash\n",
         "packaging/keep.sh": "#!/usr/bin/env bash\n"},
    )
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    tool = build_standard(standard, {"packaging/keep.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    assert not (consumer / "packaging" / "group").exists(), "the emptied parent was left behind"
    assert (consumer / "packaging" / "keep.sh").is_file()


def test_an_untracked_empty_directory_still_blocks_a_file_of_the_same_name(tmp_path: Path) -> None:
    """`is_file()` sees regular files and nothing else.

    An empty directory nobody tracked keeps the name occupied just as effectively, and pruning
    never visits it: pruning walks up from deleted files, and this one never held any.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/thing/inner.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    (consumer / "packaging" / "thing" / "untracked").mkdir()

    tool = build_standard(standard, {"packaging/thing": "#!/usr/bin/env bash\n"})
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0, "wrote a file into a directory an empty child kept alive"
    assert (consumer / "packaging" / "thing" / "inner.sh").exists(), "retired before it refused"


def test_a_kept_file_cannot_be_treated_as_a_directory_to_write_into(tmp_path: Path) -> None:
    """Upstream turned a file into a directory, and the consumer had edited that file.

    Retirement rightly keeps the edit, which leaves a regular file exactly where the new directory
    has to go. Unchecked, this reaches the copy as a bare FileExistsError, after other files have
    already been written and with the lock still describing the previous state.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/thing.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    (consumer / "packaging" / "thing.sh").write_text("#!/usr/bin/env bash\n# mine\n")

    tool = build_standard(standard, {"packaging/thing.sh/main.sh": "#!/usr/bin/env bash\n"})
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0, "wrote into a path that is not a directory"
    assert "Traceback" not in result.stderr, f"crashed rather than refusing:\n{result.stderr}"
    assert "thing.sh" in result.stderr
    assert (consumer / "packaging" / "thing.sh").read_text().endswith("# mine\n")


def test_replacing_a_file_the_standard_never_owned_is_announced(tmp_path: Path) -> None:
    """The standard starting to ship a path the consumer already filled.

    Overwriting is the right outcome — that is what adopting a shared file means — but a Renovate
    bump now performs it with nobody watching, so it cannot also be the quiet outcome.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/one.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    (consumer / "packaging" / "mine.sh").write_text("#!/usr/bin/env bash\n# local\n")
    tool = build_standard(
        standard,
        {"packaging/one.sh": "#!/usr/bin/env bash\n", "packaging/mine.sh": "#!/usr/bin/env bash\n"},
    )
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=True
    )

    assert "ADOPTED packaging/mine.sh" in result.stderr, f"silent overwrite: {result.stderr!r}"
    assert "ADOPTED packaging/one.sh" not in result.stderr, "an already-owned file is not adoption"


def test_a_symlink_to_a_retired_file_keeps_its_directory_alive(tmp_path: Path) -> None:
    """Two paths, one target. Only one of them is going away."""
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/thing/inner.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)
    (consumer / "packaging" / "thing" / "alias.sh").symlink_to(
        consumer / "packaging" / "thing" / "inner.sh"
    )

    tool = build_standard(standard, {"packaging/thing": "#!/usr/bin/env bash\n"})
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0, "treated a surviving symlink as removable"
    assert (consumer / "packaging" / "thing" / "inner.sh").exists(), "deleted before refusing"


def test_a_script_can_vendor_a_new_copy_of_itself_while_running(tmp_path: Path) -> None:
    """The ordinary case here, not an exotic one.

    `refresh-pins.sh` calls the re-vendor, and a standard bump can ship new copies of both. Bash
    reads a script incrementally by file offset, so rewriting that same inode mid-run resumes the
    interpreter at a byte position that now points into different text. The lines after the call
    then run, or do not, depending on how much the file happened to grow.
    """
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    short = "#!/usr/bin/env bash\necho step-one\n"
    tool = build_standard(standard, {"packaging/self.sh": short})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    # The running script re-vendors, which replaces the very file bash is reading, and must still
    # reach its own last line.
    runner = consumer / "packaging" / "self.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo step-one\n"
        f'"{sys.executable}" "{tool}" "{consumer}" >/dev/null\n'
        "echo step-two-after-being-replaced\n"
    )
    runner.chmod(0o755)

    longer = "#!/usr/bin/env bash\n" + "# a much longer replacement\n" * 200
    build_standard(standard, {"packaging/self.sh": longer})

    result = subprocess.run(["bash", str(runner)], capture_output=True, text=True, check=False)

    assert result.returncode == 0, f"the running script broke: {result.stderr}"
    assert "step-two-after-being-replaced" in result.stdout, (
        f"execution did not survive the rewrite: {result.stdout!r}"
    )
    assert runner.read_text() == longer, "the new version did not land for the next run"


def test_a_symlink_where_a_file_belongs_is_replaced_not_followed(tmp_path: Path) -> None:
    """Renaming over a symlink replaces the link. Writing through one would edit its target."""
    standard = tmp_path / "standard"
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    tool = build_standard(standard, {"packaging/one.sh": "#!/usr/bin/env bash\n"})
    subprocess.run([sys.executable, str(tool), str(consumer)], capture_output=True, check=True)

    target = consumer / "target-dir"
    target.mkdir()
    (target / "witness.txt").write_text("untouched\n")
    (consumer / "packaging" / "linked.sh").symlink_to(target)

    tool = build_standard(
        standard,
        {"packaging/one.sh": "#!/usr/bin/env bash\n", "packaging/linked.sh": "#!/usr/bin/env bash\n"},
    )
    result = subprocess.run(
        [sys.executable, str(tool), str(consumer)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, f"aborted midway instead of replacing the link: {result.stderr}"
    link = consumer / "packaging" / "linked.sh"
    assert link.is_file() and not link.is_symlink(), "the symlink survived where a file belongs"
    assert (target / "witness.txt").read_text() == "untouched\n", "wrote through the symlink"


def test_every_shared_file_lands_where_consumers_are_configured_to_keep_it() -> None:
    """Renovate discards post-upgrade changes outside its `fileFilters`.

    Consumers enumerate those filters, so `shared/` is not free to grow anywhere it likes: a file
    shipped outside the agreed shape is written on the update branch, dropped before the commit,
    and leaves a lock describing content the branch does not have. The bump fails for a reason
    visible in neither repository. Consumers assert their filters cover everything already in the
    lock; only this end can refuse the first file that escapes them.

    Widening this list means widening every consumer's `fileFilters` in the same change.
    """
    # Mirrors what both consumers actually list. `.github/` is not a prefix there: they retain one
    # exact path inside it, so a second file added beside the template would be dropped.
    allowed_prefixes = ("packaging/", "tests/release/")
    allowed_files = {".editorconfig", ".github/PULL_REQUEST_TEMPLATE.md"}

    shared = ROOT / "shared"
    stray = sorted(
        str(p.relative_to(shared))
        for p in shared.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and str(p.relative_to(shared)) not in allowed_files
        and not str(p.relative_to(shared)).startswith(allowed_prefixes)
    )
    assert not stray, (
        f"these would be vendored and then discarded by every consumer's fileFilters: {stray}"
    )
