#!/usr/bin/env python3
"""Diff two sibling projects' capabilities, by what is WIRED rather than what is mentioned.

    tools/capability-diff.py ../whiskerless ../dreame-valetudo

Working from a findings list or a same-path file diff makes one whole class of divergence
invisible: anything one project simply does not have. That is how an entire package-repository
channel, a coverage gate and an asset-naming scheme all went unnoticed here.

Every probe below asks whether something is CALLED or CONFIGURED, never whether a word appears.
A scaffolded-but-unwired script must read as absent, because to a user it is.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# name -> (regex, where to look). Deliberately anchored on call sites and config keys.
PROBES: dict[str, tuple[str, str]] = {
    # Anchored on an actual call site: a scaffolded-but-uncalled script must read as absent,
    # because to a user it is.
    "apt/dnf repository": (r"^\s*(?:bash\s+)?\S*publish-registry\.sh\s", "workflows"),
    "package signing": (r"NFPM_SIGNING_KEY_FILE", "packaging"),
    "homebrew bottles": (r"build-bottles\.sh|bottle_block|bottle do", "any"),
    "HACS": (r"hacs\.json|hassfest", "any"),
    # A PUBLISHED single-file download, not merely a onefile build mode: dreame builds onefile for
    # macOS but ships Linux as onedir trees inside packages, so it has no such asset.
    "standalone linux binary": (r"-linux-\$\{?(?:ARCH_BIN|arch)\}?\b|-linux-x86_64\b", "workflows"),
    # Either spelling of the version variable: whiskerless converts in place, dreame keeps the raw
    # tag in VERSION and derives PKGVER for filenames. Scoped to the whole tree, not the workflows:
    # both build the filename in packaging/build-linux-arch.sh, so a workflow-only search reports a
    # gap for whichever project does not also mention the variable in a workflow.
    "versioned asset names": (r"_\$\{(?:VERSION|PKGVER)\}_|-\$\{(?:VERSION|PKGVER)\}\.", "any"),
    "release-time coverage gate": (r"cov-fail-under", "release_workflows"),
    "coverage gate": (r"--cov-fail-under", "workflows"),
    "external-source link gate": (r"check-external-links\.sh", "workflows"),
    "package/staging parity": (r"check-package-parity\.py|package parity ok", "workflows"),
    "vendored-standard drift lock": (r"check-standard-sync\.py", "workflows"),
    # The CLI FEATURE, distinct from the smoke test that proves `apt-get remove` works. Both
    # projects can be installed through several channels at once (Homebrew and the .pkg both place
    # the binary), so "which copies of me exist and how do I remove each" is a real user question.
    "uninstall command + install detection": (
        r'cmd == "uninstall"|\bdef find_installs\b', "source"
    ),
    "install lifecycle (upgrade+remove)": (r"deb-lifecycle|prove uninstall removes|apt-get remove", "any"),
    # The MATRIX, not a token that happens to appear in one Dockerfile. This matched
    # `DEBIAN_FLOOR_IMAGE` and reported parity while one project ran a 44-stage install smoke
    # across five distributions and the other had five stages and no matrix workflow at all.
    # Both publish every release to THREE registries. Only one checks afterwards that all three
    # actually serve the same bytes, and refills the ones that do not from a content quorum. A
    # failed upload to one registry is otherwise permanent and silent.
    "cross-registry reconcile": (r"present", "reconcile"),
    "multi-distro install matrix": (r"present", "install_matrix"),
    # Retrying a GitHub runner that died in `Set up job`, before any of our steps ran. Nothing
    # project-specific about it, and re-running by hand trains people to re-run red builds.
    "automatic infra-failure retry": (r"present", "infra_retry"),
    # The gate SKIPS a fork PR so untrusted code never runs beside release credentials. That is
    # only half the answer: without a mirror workflow the contributor then gets no checks at all.
    "PR CI for outside contributors": (r"present", "pr_ci"),
    "fork-PR trust gate": (r"head\.repo\.full_name\s*==\s*github\.repository", "workflows"),
    # --- product surface, not just infrastructure. The first inventory stopped at channels and
    # gates, which is why UX and safety differences stayed invisible.
    # Not that a CONTRIBUTING file exists — that it names what will not be broken. Without it
    # every symbol is potentially load-bearing and nothing can be refactored with confidence.
    "documented stability contract": (r"promises not to break", "contributing_text"),
    "CONTRIBUTING guide": (r"^", "contributing"),
    "issue templates": (r"^", "issue_templates"),
    "per-command --help": (r"only=|add_parser|subparsers", "source"),
    "injectable console seam": (r"class Console|_console\b|console\.say", "source"),
    "typed project exceptions": (r"class \w+Error\(|class Die\(|raise \w+Error\(", "source"),
    "durable write (parent fsync)": (r"os\.fsync\((?:directory|dir_fd)", "source"),
    "concurrent-writer locking": (r"fcntl\.flock|LOCK_EX", "source"),
    "symlink refusal on state": (r"is_symlink\(\)|O_NOFOLLOW", "source"),
    "layout version + refusal": (r"LAYOUT_VERSION|layout_version", "source"),
    "min upgrade version in marker": (r"min_tool_version", "source"),
    "diagnostic scrubber": (r"def scrub\(", "source"),
    # By the MAPPING, not the name: a refusal type that is defined but handled as a generic error
    # still exits 1, and the caller still cannot tell "I declined" from "it broke".
    "safety refusal has its own exit code": (
        r"except (?:SafetyStop|SafetyError)\b(?:.*\n){0,12}?.*\breturn 2\b", "source"
    ),
    "update-available nudge": (r"update_check", "source"),
    "Keep a Changelog + SemVer declared": (r"Keep a Changelog", "changelog"),
    "machine-readable project URLs": (r"\[project\.urls\]", "pyproject"),
    # A secret must reach the process out of band — a file, the environment, or stdin — because
    # argv is world-readable in `ps`. The FORM differs by what the secret is (whiskerless takes a
    # wifi password from a file or env; dreame streams the miio key over stdin), so probing for one
    # project's spelling reported the other as missing a capability it has in a stronger form.
    "secret kept out of argv": (
        r"--wifi-pass-file|_WIFI_PASSWORD_ENV|read_secret_file|stdin_path=", "source"
    ),
}


# Some probes are about a file EXISTING rather than a pattern appearing.
PRESENCE = {
    "contributing": ("CONTRIBUTING.md",),
    # The FILE, not a mention of it: prose describing the workflow is not the workflow, and a probe
    # that reads file contents happily matches the sentence in CONTRIBUTING.md that documents it.
    "pr_ci": (".github/workflows/ci-pr.yml",),
    "install_matrix": (".forgejo/workflows/install-matrix.yml",),
    "reconcile": ("packaging/reconcile-releases.sh",),
    "infra_retry": (".github/workflows/retry-infra-failures.yml",),
    "issue_templates": (".github/ISSUE_TEMPLATE",),
}
#: scope -> the single file to read, for probes about one document's contents.
SINGLE_FILE = {"changelog": "CHANGELOG.md", "pyproject": "pyproject.toml",
               "contributing_text": "CONTRIBUTING.md"}


def corpus(repo: Path, scope: str) -> str:
    # Tracked AND untracked-but-not-ignored: this is a working-tree convergence check, and a
    # capability added but not yet committed is still a capability. Reading only `ls-files` made a
    # brand-new module read as absent.
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    if scope in SINGLE_FILE:
        try:
            return (repo / SINGLE_FILE[scope]).read_text(errors="replace")
        except OSError:
            return ""
    if scope in PRESENCE:
        hit = any(n.startswith(pre) for n in listed for pre in PRESENCE[scope])
        return "present" if hit else ""
    chunks = []
    for name in listed:
        if scope == "workflows" and "/workflows/" not in name:
            continue
        # The release path specifically: ci.yml gating something proves nothing about what a
        # RELEASE is allowed to ship, and that difference hid a real gap.
        if scope == "release_workflows" and not any(
            name.endswith(f"/workflows/{stem}.yml") for stem in ("release", "prerelease")
        ):
            continue
        if scope == "packaging" and not name.startswith("packaging/"):
            continue
        if scope == "source" and not (name.endswith(".py") and not name.startswith("tests/")):
            continue
        try:
            chunks.append((repo / name).read_text(errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    a, b = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    # Derived from the probes rather than listed: a hand-maintained list means adding a probe in a
    # new scope raises KeyError at the point the answer was wanted.
    texts = {
        scope: (corpus(a, scope), corpus(b, scope))
        for scope in sorted({scope for _, scope in PROBES.values()})
    }
    # A gap is acceptable ONLY if it is written down. That is the whole rule: every difference is
    # either converged or recorded with its reason. Unrecorded is how a package-repository channel,
    # a coverage gate and an asset-naming scheme all sat unnoticed between two sibling projects.
    variance = (Path(__file__).resolve().parent.parent / "VARIANCE.md").read_text().lower()

    gaps = []
    print(f"{'CAPABILITY':<38}{a.name:>14}{b.name:>18}")
    for name, (pattern, scope) in PROBES.items():
        ta, tb = texts[scope]
        ha, hb = bool(re.search(pattern, ta, re.M)), bool(re.search(pattern, tb, re.M))
        # The probe's own name, verbatim. Matching its individual words anywhere in the document
        # silenced a gap whenever ordinary prose happened to use them all — which is how a broken
        # probe sat here reporting a difference that did not exist, with nothing drawing attention
        # to it. Recording a variance has to be a deliberate act naming the capability.
        recorded = ha == hb or name.lower() in variance
        flag = "" if ha == hb else ("   gap (recorded)" if recorded else "   GAP — UNRECORDED")
        if ha != hb and not recorded:
            gaps.append(name)
        print(f"  {name:<36}{'yes' if ha else '-':>12}{'yes' if hb else '-':>16}{flag}")
    print()
    if gaps:
        print("UNRECORDED GAPS — close them, or write the reason into VARIANCE.md:")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("No unrecorded gaps: every difference is converged or written down.")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
