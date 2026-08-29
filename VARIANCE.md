# Recorded variance

Deliberate differences between `whiskerless` and `dreame-valetudo`. Anything not recorded here is
drift, and drift is a defect.

A variance is legitimate when it names a real capability or product difference, and when the
**observable guarantee** is still shared. "The other project does not do this" is not a variance;
it is a gap wearing a variance costume.

**Three kinds of entry live here, and conflating them is what made this list read worse than
reality.**

1. **Genuine divergence.** The two projects do different things because they *are* different
   things, and converging would make one of them worse: execution model, public API surface,
   licence, HACS.
2. **One rule, two correct outputs.** A single shared rule applied to different inputs. These are
   *convergence*, not divergence — "pin what you control, float what your consumers must resolve"
   produces floors in one repo and exact pins in the other because only one has consumers. Listing
   them as differences was a mistake.
3. **Converged, kept for the reasoning.** Things that used to differ. Kept because the *why* is
   worth reading — several were solved twice, independently, by two projects that did not know the
   other had hit the same bug.

There is a fourth category: gaps recorded as open. It is **empty** — see the bottom of this file.
An open gap goes there, under its own heading, so it can never be mistaken for a decision.

---

## The state, in one place

**Genuine divergences — four.** Execution model (async vs strictly-ordered synchronous), public API
surface (a library with consumers vs a CLI that is the contract), licence (MIT vs GPL-3.0), and
HACS (one ships a Home Assistant integration; the other has no Home Assistant surface to expose).
Each is a consequence of *what the project is*, and converging any of them would make one worse.

**Converged during the 2026-08-20 pass**, having previously differed: the vendored shared standard
and its drift lock, the rc sweep and its retention gates, versioned artifact filenames, coverage
floors and where they are gated, package signing under one namespace key, the apt/dnf repository,
Homebrew bottles, the standalone Linux download, the `src/` layout, the Renovate policy, fork-PR CI,
cross-registry reconcile, the install matrix, automatic infra-failure retry, the stability contract,
`uninstall` + install detection, the `Robot`/`ModelSpec` vocabulary, and the first-person voice in
both READMEs.

**Queued, not divergent**: nothing. The PyInstaller policy and the move of arm64 work to native
runners were the last two, and both are done — see that section.

**Open gaps: none.**

---

## Architecture

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| **Execution model** | `async` throughout | synchronous, strictly ordered |
| **Why** | Long-lived evented work: MQTT subscriptions, BLE sessions, a Home Assistant coordinator | Ordered destructive hardware work: FEL, fastboot, SSH, flashing. Concurrency buys nothing and costs determinism |
| **Still shared** | Identical consent, validation, attempt, effect, postcondition, interruption and recovery semantics. The guarantees converge; the mechanism does not |

**Do not** convert either. Forcing Dreame's flash sequence into an event loop, or Whisk's transport
loops into blocking calls, would add risk without improving anything a user can observe.

## Product shape

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| **Surface** | Consumed Python library + CLI + Home Assistant integration | Application and CLI |
| **Public API** | Curated facade with `__all__`, `py.typed`, and a compatibility promise | CLI is the contract; modules are internal |
| **Consequence** | Renames need aliases, deprecation windows, and installed-artifact compatibility tests | Modules may be refactored freely; the CLI grammar may not |

## Licence

**Whiskerless is MIT. Dreame Valetudo is GPL-3.0-or-later.** A genuine divergence, and one of the
few: the same question asked twice, with two different correct answers, because the two projects
are consumed differently.

- **MIT for whiskerless, because Home Assistant imports it.** The integration declares
  `whiskerless==<version>` and HA installs it from PyPI, so the library runs inside HA's own
  process. HA Core is Apache-2.0 and network-served by definition. Copyleft here would reach the
  combined work — anyone shipping an HA appliance image, or running HA for other people, would owe
  source for it — and it would permanently foreclose becoming an official integration, since Core
  does not accept copyleft dependencies. `pylitterbot`, the library behind the official
  `litterrobot` integration and the direct model for this one, is MIT.
- **GPL-3.0 for dreame-valetudo, because nothing imports it.** A standalone local tool, so copyleft
  costs its users nothing and keeps changes open. It was AGPL-3.0-or-later until 2026-08-20; AGPL's
  distinguishing clause reaches software modified and offered *over a network*, which a USB CLI
  can never trigger. It was paying the cost of the most feared licence for a clause that cannot
  fire. Peer evidence: `dustcloud` and `python-miio`, the two projects closest to what this one
  does, are both GPL-3.0; Valetudo itself is Apache-2.0; nothing in the ecosystem uses AGPL.

Each repo's `CONTRIBUTING.md` carries the full reasoning, including what third-party code ships
alongside and whether it is **linked** or merely **executed** — `sunxi-fel` is GPL-2.0 and runs as
a separate process, which is aggregation rather than a combined work. Keep the SPDX metadata and
`LICENSE` accurate in each.

## Layout and dependencies

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| **Source layout** | `src/` package | `src/` package — **converged 2026-08-20** |
| **Dependency policy** | Library-compatible **lower bounds**, so downstreams can resolve | Application **exact pins** plus a committed `uv.lock` |
| **Still shared** | Both exercise the literal interpreter floor in CI. Both exact-pin the *development* toolchain (ruff/mypy/pytest), because a lint release must never redden `main` with no code change |
| **Where that toolchain pin lives** | `pyproject.toml` alone; the workflows grep the version back out of it | `pyproject.toml` **and** `uv.lock` **and** annotated literals in the workflows, kept equal by `test_pinned_toolchain_matches_the_lockfile` |

Both pin exactly and both are raised by Renovate's `pep621` manager. What differs is how many copies
of the version exist. Whiskerless keeps one: its workflows install the dev extra straight from
`pyproject.toml`, so a second copy would be a second source of truth for something already stated.
Dreame Valetudo's workflows `pip install` the version as a literal while `uv run` resolves it from
`uv.lock`, so the same number lives in three kinds of place — `pyproject.toml`, `uv.lock`, and a
literal in each workflow that lints or tests, currently seven physical copies. The `pyproject.toml`
pin is `==` rather than a floor precisely so `pep621` has something to raise: that is what lets the
lockfile relock in the same PR as the literals instead of trailing a commit behind.

Neither shape is better in the abstract. Whiskerless needs no agreement check because it has nothing
to keep in agreement; Dreame's seven copies are only safe because
`test_pinned_toolchain_matches_the_lockfile` compares every one of them against `uv.lock`. It did
not always: it read a single workflow, and a ruff bump duly reached the Forgejo workflows,
`pyproject.toml` and the lockfile while GitHub's PR lint stayed a release behind, silently.


Both use `src/` now. Dreame was flat, and the argument for leaving it there was that the risk `src/`
mitigates — a module missing from the built wheel still passing every test, because a flat layout
lets `pytest` import from the working directory — was already covered by an installed-wheel smoke
test. True, but it made the two repos structurally different for a reason no reader could see, and
the migration turned out to be mechanical: 341 references, all of them paths rather than imports.

The one thing it changes for a contributor: **the package is not importable from the checkout root,
so anything running the tests has to install it first.** Two CI jobs installed only the toolchain
and relied on the flat layout without saying so; both now `pip install -e .`.

## Channels

| Channel | Whiskerless | Dreame Valetudo | Note |
|---|---|---|---|
| `.deb` / `.rpm` release assets | yes | yes | Both versioned, both signed |
| apt / dnf repository | yes | yes | One `sisyphusmd.repo` + `sisyphusmd-testing.repo` per repo, one owner-wide key |
| Homebrew formula (stable + `-rc`) | yes | yes | Same tap, same fall-through rule |
| Homebrew bottles | yes | yes | Same four platforms; **benefit differs** — see *Homebrew bottles* |
| Standalone Linux download | one-file binary | onedir bundle tarball | Different freezing constraints, same guarantee: extract and run |
| macOS `.pkg` (signed + notarized) | yes | yes | |
| Source tarball | PyPI sdist | byte-reproducible tarball | Both feed the formula |
| PyPI / `pipx` / `uvx` | yes | yes | Both publish from `publish.yml` with a project-scoped token; the tap formula builds from the sdist in both |
| **HACS** | **yes** | **no** | The one remaining variance. Predicate genuinely false: there is no Home Assistant integration to ship |
| Native Windows | unsupported | unsupported | Both. WSL never counts as native evidence |

**HACS is the only row where one project has a channel the other does not**, and it is not a gap:
whiskerless ships a Home Assistant integration, and dreame-valetudo is a USB rooting tool with no
Home Assistant surface to expose. There is nothing to converge.

## Artifact naming — converged, and why it mattered

**Both projects now carry the version in artifact filenames**, in the native package form:

```
whiskerless_0.2.0~rc.35_amd64.deb        dreame-valetudo_0.3.0~rc.17_amd64.deb
```

Dreame's used to be `dreame-valetudo_amd64.deb` — two downloads in `~/Downloads` that could not be
told apart, where the second silently overwrote the first. The tilde is deliberate: nfpm normalises
a semver prerelease to that form internally, so a filename built from the raw tag would say
`-rc.17` while `dpkg -I` reported `~rc.17`, and the file would not be named after what it contains.

**The consequence both now share:** GitHub rewrites `~` to `.` in the *stored* asset name and
enforces uniqueness on the rewritten form, while Forgejo stores it verbatim. The shared publisher
normalises for lookup and upload while still comparing bytes against the local file
(`rel_github_asset_name`, pinned by test with both projects' real filenames).

This was previously recorded here as a *variance* — Dreame being immune because its filenames
carried no version. That was safety by accident, and it was the accident that made the missing
version look acceptable. Both are now converged and both are protected by the same code.

## PyPI publishing — Forgejo, with a token, in both

Both projects upload from `publish.yml` on Forgejo using `twine` and a **project-scoped**
`PYPI_API_TOKEN` (`whiskerless-forgejo-ci`, `dreame-valetudo-forgejo-ci`). Converged, and staying
that way.

**Trusted Publishing was considered and rejected**, so that it does not get re-proposed. It would
remove the upload token entirely — PyPI mints a short-lived OIDC credential instead, and records a
PEP 740 attestation tying each artifact to the workflow that built it. The cost is that PyPI only
accepts OIDC from GitHub Actions, GitLab.com, Google Cloud and ActiveState, never from a
self-hosted Forgejo, so publishing would have to move to GitHub.

That is the wrong trade for these projects. GitHub is used **only for what requires it** — macOS
runners for notarization, arm64 runners, and the HACS pointer — and PyPI publishing requires none
of it. Adding a fourth dependency to remove a credential is a poor exchange when the Forgejo runner
already holds the GPG signing key, three registry push PATs and the tap write PAT: one
project-scoped PyPI token is not a meaningful change to that blast radius, while a third party on
the publishing path is a meaningful change to the architecture.

Revisit only if the calculus changes — if PyPI ever accepts OIDC from self-hosted forges, this
becomes free and should be taken.

## The Homebrew tap — converged onto one shared script

`packaging/update-tap.sh` is now **vendored**, not duplicated. Both projects run the same file,
parameterised by `project.env`, so the two cannot drift apart again — which is what the standard
exists for.

Getting there meant closing the last real difference: **where the formula's source archive comes
from.** whiskerless's formula built from its PyPI sdist; dreame-valetudo's built from a
hand-rolled release tarball, because it did not publish to PyPI at all. It does now, so both build
from the sdist, verified the same way: the checksum comes from a LOCAL build of the tag, and PyPI
is required to be serving exactly those bytes. A registry download is what the checksum protects
users from, so it is never the source of it.

`PROJECT_FORMULA_SOURCE` existed for about a day to describe that difference, and is deleted.

**One trap worth keeping written down.** PEP 625 normalises the sdist FILENAME — `-` becomes `_` —
while the directory segment keeps the published name:

```
https://files.pythonhosted.org/packages/source/d/dreame-valetudo/dreame_valetudo-0.2.1.tar.gz
                                                 ^ project name    ^ normalised filename
```

The hyphenated filename returns 404. whiskerless has no hyphen in its name, so it never saw this;
the shared script derives both spellings rather than being told either.

**Still one-sided, and correctly so:** whiskerless publishes to PyPI because its Home Assistant
integration pins `whiskerless==<version>` and resolves it from there. dreame-valetudo publishes
because it is the install channel users are pointed at, and now because the formula builds from it.
Same mechanism, two different reasons, no flag needed to express that.

## One rule, two correct outputs — NOT divergences

Each of these looked like a difference and is the opposite: a single rule, applied honestly to
different facts. They are listed together because seeing them as a group is what stops the next
reader "fixing" one of them.

| The shared rule | whiskerless | dreame-valetudo |
|---|---|---|
| **Pin what you control, float what your consumers must resolve** | runtime deps are floors (`aiomqtt>=2.0.0`) — a library that exact-pins cannot be installed alongside anything else | everything exact-pinned plus a committed `uv.lock` — nothing resolves against it, so the tested build IS the shipped build |
| **A secret never touches the command line** (`ps` is world-readable) | `--wifi-pass-file`, an env var, or a TTY prompt; the argv flag survives because it is documented and scripted against, and warns once | streamed over stdin, because its secrets are generated by the tool rather than typed by a person — there is no argv route to deprecate |
| **Name the artifact after what the packaging system reports** | `~rc.` in `.deb`/`.rpm` filenames, matching what `dpkg -I` says | the same, plus `-rc.` for the `.pkg`, because `pkgbuild --version` stores the tag form verbatim |
| **Never let a consumer see a version it cannot yet install** | `releases` waits on `pypi`: HACS offers the update the instant the GitHub release exists, and the manifest pins `whiskerless==<version>` | `releases` runs beside `pypi` off `guard`: nothing watches its release feed and then resolves the version somewhere else |
| **Do not rebuild what the package manager already ships** | `cryptography` is `depends_on`, not a resource: its sdist is a Rust extension, and Homebrew bottles it for every targeted platform | both resources stay resources: neither `sunxi-tools` nor `pyusb` exists as a Homebrew formula, so there is nothing to defer to |
| **Hold the one seam higher than the average** | `safety.py` at 100% — every send funnels through it | `run.py` at 100% — every external command funnels through it |

Both also pin their **development** toolchain exactly, at the same versions: a lint release must
never redden `main` with no code change. That half was genuine drift and was fixed.

**Why this section exists.** Three of these four were written up as divergences, which made the
list read as though the projects disagreed about something. They never did. A rule that produces
two different outputs from two different inputs is convergence working correctly — and calling it
divergence invites someone to "converge" it by forcing one project to do something wrong for it.

## Vocabulary — two collisions fixed, two kept

**Fixed 2026-08-20**, because both were internal and cost nothing to rename:

| Was | Now |
|---|---|
| `Profile` meant "a saved robot record" in whiskerless and "a supported-model spec" in dreame | dreame's is `ModelSpec` in `models.py`; the bare word `Profile` now appears nowhere in either repo, only the compound `RobotProfile` |
| `tests/integration/` meant "the Home Assistant pytest package" in whiskerless and "shell release-script tests" in dreame | both use `tests/release/` for shell tests; `tests/integration/` means only the HA package |

A rename that would have created a NEW collision was declined: making whiskerless's `RobotProfile`
into `Robot` was the obvious symmetry, but `robot` is already a variable name there in 1367 places
holding `LitterRobot4State` — the *live* state. `Robot` would then have meant "saved config" in one
repo and "per-robot work directory" in the other, which is the problem, not the fix.

**Kept, and documented instead**, because these are stable public CLI verbs and the words are
applied *consistently* — each tool preserving the irreplaceable state it owns:

| Verb | Whiskerless | Dreame Valetudo |
|---|---|---|
| `backup` / `restore` | the local credential store on this machine | live factory capture and stock restoration on the robot |
| `status` | live robot state | workflow progress |

Renaming these means breaking public CLI verbs for no gain. Both already use `robot` for the device
and `forget` for removing a saved record. Help text and documentation must make the distinction
explicit; do not mechanically rename either side without a compatibility plan.

The only class names now shared between the two repos are `Console` and `Serial`, and both mean the
**same thing** in each — `Serial`'s docstrings are nearly identical. That is convergence, not
collision, and it is what the rest of this table should eventually look like.

---

## Discovered 2026-08-20, during the convergence pass

### Contribution routing

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| Issues and PRs | **GitHub** — it is the mirror HACS installs from, and where users already are | **Forgejo** — GitHub is a push-mirror except `release-macos.yml` |
| Consequence | needs `.github/workflows/ci-pr.yml` so fork PRs get CI on GitHub-hosted runners | needs no GitHub PR CI at all; its fork gate lives on the Forgejo side |

Not a gap. Whisk's `ci-pr.yml` having no Dreame counterpart is this decision, not an omission.

### Coverage floors — now converged

| | Whiskerless | Dreame Valetudo |
|---|---:|---:|
| Repository floor | **99%** | **99%** |
| Measured | 99.04% (library), 99%+ (integration) | 99.11% |
| The one seam, gated separately | `safety.py` **100%** — the chokepoint every send funnels through | `run.py` **100%** — the Runner seam every external command funnels through |
| Gated in CI | yes | yes |
| Gated on the RELEASE path | yes | yes |

Both floors are **measured non-regression baselines**, not aspirations, and both hold their one
unavoidable seam at 100 so a regression there cannot hide inside the repository average.

Dreame's floor was 86 with its seam at 95, and — the part that actually mattered — its release and
prerelease workflows ran the suite with no coverage gate at all. `ci.yml` runs on a branch; a
release is cut from a tag, so the release path was the one route by which a coverage regression
could ship. Whiskerless gated all three; Dreame gated one. Both now gate all three.

### Renovate policy — converged

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| Automerges on green | `patch`, `minor`, `digest`, every dependency | the same |
| Holds | the release-only build pins, and `bleak` | `pyusb`, and the manylinux images |
| Every hold states what CI cannot reach | yes, pinned by test | yes, pinned by test |

**One rule, two lists**, so this belongs with the entries above rather than among the divergences: a
hold is legitimate only where a green run says nothing about the risk, and the two projects reach
their robots over different transports. `bleak` is faked at its boundary and no runner has a
Bluetooth radio; `pyusb` is stubbed into `sys.modules` and no runner has a robot on the end of a
cable. Neither project can buy that coverage, so both hold, and both must say so in `prBodyNotes`
where the reviewer sees it — `test_every_renovate_hold_says_what_CI_cannot_reach` in whiskerless,
`test_every_hold_says_what_CI_cannot_reach` in dreame-valetudo.

The manylinux images are held in both for a different reason that is the same shape: they define the
shipped glibc ABI, nothing in PR CI builds with them, and the blast radius is every Linux package.

This was previously recorded as an open tension, on the grounds that dreame ran a no-holds policy
that a test enforced while its own rules described hand review. That test no longer exists and the
policy it enforced is gone; both projects allow documented holds. The tension was between the record
and the repositories, not between the two repositories.

### Development toolchain — now converged

Both exact-pin `ruff`, `mypy`, `pytest` and `pytest-cov` at the **same versions**, each with a
`# renovate:` marker. Whiskerless floated these until 2026-08-20; a ruff release could redden its
`main` with no code change. Runtime dependencies stay floors in Whiskerless because it ships as a
consumed library, and stay pinned in Dreame because it ships as an application — that half remains
variance, recorded above under *Layout and dependencies*.

### Input discovery — now converged

Both lint and shellcheck **discover** their inputs (`git ls-files`) rather than enumerating them.
Both previously used hand-maintained lists, and in both a newly added file went unchecked with no
symptom. Dreame's one deliberate exclusion, `docs/research/tools/`, is pinned by a test so widening
it is a visible edit.

---

## PyInstaller onefile vs onedir — one bug, two fixes, and then the bug went away

Both projects freeze a Python app with PyInstaller, and both used to cross-build arm64 on an amd64
runner under BuildKit's QEMU. Both hit **GHSA-9fxf-4qw3-ghmr** — PyInstaller 6.22.1 made a onefile
app verify that its parent process runs the same executable, and under emulation the parent
resolves to `/dev/.buildkit_qemu_emulator`, so every emulated run died with *"Security validation
failure: parent process has different executable!"*.

**Both lost a release candidate's Linux artifacts to it**, separately: Whiskerless `v0.2.0-rc.18`,
Dreame `rc.13`. Neither fix reached the other until this audit.

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| Fix at the time | Pin PyInstaller at **6.22.0**, before the check took effect on POSIX | Move Linux to **onedir**, which spawns no child so the check never runs |
| Cost | Held back on an old PyInstaller; needed a standing watch script | No single-file Linux download; ships bundle trees inside packages |

**Neither fix is load-bearing any more.** Both projects now build each architecture on its own
hardware — amd64 on the Forgejo runner, arm64 on GitHub's native arm runner, nothing emulated
anywhere — and a natively-built onefile app's parent is the app. The bug cannot occur. So the pin is
gone from Whiskerless along with its watch script, and PyInstaller tracks upstream in both.

**Two separate decisions live here, and merging them produces confident wrong answers.** They were
merged in this entry until 2026-08-24, and the reader who merged them argued twice that dreame's
helper executables require onedir. They do not: macOS ships those same helpers beside a **onefile**
app.

**Decision 1 — the bundle mode: invisible in what you download, visible in how it runs.** It
governs how PyInstaller lays out one frozen app. In the PACKAGED channels — `.pkg`, `.deb`, `.rpm`,
the tap — it changes no filename and no channel, because a package wraps either shape. It reaches
the standalone channel directly, which is Decision 2 below: a bare executable is only possible
because whiskerless is onefile. And it is not cosmetic anywhere: onefile unpacks on every invocation and needs
an executable temp dir, which is behaviour a user meets at runtime. Whiskerless uses onefile everywhere. Dreame
chooses per platform, with different footing under each — the macOS choice is platform-driven, the Linux one is not:

| | Mode | Why, today |
|---|---|---|
| Dreame, macOS | onefile | one Mach-O to codesign per frozen app, not an executable plus every `.so` |
| Dreame, Linux | onedir | retained shape; avoids needing an executable temp dir (see below) |
| Whiskerless, both | onefile | short-lived, infrequent runs; a single file is the friendlier artifact |

Notarization is not the reason: `notarytool submit` and `stapler staple` act on the finished `.pkg`
whatever its insides look like. What onefile saves is codesigning surface — one Mach-O per frozen
app instead of the executable plus every shared object beside it. That much is demonstrable.

**What the Linux side rests on is thinner, and this entry has been rewritten twice for claiming
otherwise.** Two rationales were offered and neither survived: that dreame's helper executables
require onedir (macOS ships the same helpers beside a onefile app), and that dreame pays onefile's
per-invocation unpack repeatedly. It would pay it TWICE — the outer process unpacks, then re-execs
itself under tmux, which unpacks again — and then not at all, because the session is long-lived.
Bounded, not recurring. What actually remains:

- **Real, and the only technical point standing:** a onefile app extracts to a temp directory and
  execs from there, so it cannot run where `TMPDIR` is mounted `noexec`. A onedir bundle never
  touches temp. Nobody has reported hitting this, so treat it as a property rather than an incident.
- **Honest, and the reason to leave it alone:** the standalone channel ships this tree, and churning
  a shipped artifact's layout to make two unrelated projects match is uniformity, not convergence.

So: macOS onefile is platform-driven. Linux onedir is retained shape with one residual robustness
property. Recording it as fully platform-driven would repeat the overclaim this rewrite exists to
remove — and whoever revisits it should know the original cause (the QEMU bootloader check) is dead,
so the question is open rather than settled by history.

**Decision 2 — the standalone download shape.** This is the only place the difference reaches the
download itself. Decision 1 does reach it — a onedir app is a tree and cannot ship as a bare
executable — but the helpers would demand a container even if the mode were onefile, so the two
reasons compound rather than either standing alone:

- **Whiskerless ships one bare binary.** It has no helper executables — its work is MQTT and BLE
  through in-process Python libraries — so a single file is the whole tool.
- **Dreame ships a `.tar.gz`** of the tree with a launcher that exports `DREAME_LIBEXEC`, because
  the download must carry `dreame-fastboot` and `sunxi-fel` alongside the app. `sunxi-fel` is a C
  program from `linux-sunxi/sunxi-tools`; the Allwinner FEL protocol has no Python implementation.

Every other channel is one download in both projects. What that download then needs differs and is
worth stating precisely: the macOS `.pkg` carries its own dylibs and `tmux` into `libexec`, so it
installs without reaching the network, while the `.deb` and `.rpm` declare runtime dependencies —
libusb, libfdt, curl, ssh, tmux and the archive tools among them — that apt or dnf resolve at
install time. Neither is a defect; a
distro package that vendored its dependencies would be the wrong artifact. (Dreame separately
downloads a stage1 payload and Valetudo itself while running, because putting those on a robot is
the job.) Changing either decision now would churn a
shipped artifact to make two unrelated projects look alike, which is uniformity rather than
convergence.

One rule — build natively, freeze once, ship something a user can extract and run — with two
correct outputs.

**Consequence for channels — now closed.** Dreame used to publish no standalone Linux download at
all: a user on Arch, Alpine or NixOS had the source tarball or nothing. That was recorded here as a
*consequence* of the onedir decision, which was true, and as unavoidable, which was not.

It now publishes `dreame-valetudo-<version>-linux-<arch>.tar.gz` — the onedir tree packed, with a
launcher that resolves its own directory and exports `DREAME_LIBEXEC` so the extracted bundle finds
its own helpers instead of a system install. No PyInstaller pin, no onefile. `build-linux-tarball.sh`
assembles it from the raw bundles rather than the `.deb`, because every symlink nfpm writes is
absolute and useless in a tree the user extracts under `~/Downloads`; `smoke-linux-tarball.sh`
extracts it somewhere arbitrary in a clean container and runs it, both directly and through a PATH
symlink.

That tarball was the exit Whiskerless would have needed had the pin outlived emulation. It did not,
so Whiskerless keeps onefile; the entry above framed the choice as onefile-or-nothing, and it was
never that.

## Homebrew bottles — now in both, with the benefit stated honestly

Both projects build bottles on the same four platforms (`arm64_sequoia`, `sequoia`,
`x86_64_linux`, `arm64_linux`) through the same shared `build-bottles.sh`, `bottle-block.py` and
`render-formula.sh`, and both write the `bottle do` block in a second tap pass.

**The benefit is not equal, and pretending otherwise would be the dishonest version of parity:**

| | Whiskerless | Dreame Valetudo |
|---|---:|---:|
| Python `resource` blocks in its formula | **11** | **1** (`pyusb`, pure Python) |
| Declared runtime dependencies | `aiomqtt`, `bleak`, `cryptography`, … | **none** (`dependencies = []`) |
| What a bottle avoids | compiling `cryptography`'s Rust extension — `rust` → `llvm`, ~2.4 GB and minutes on every user's machine | creating a virtualenv and installing two pure-Python distributions — seconds |

Dreame's bottles were added for channel parity and so the mechanism exists, is exercised and stays
working, not because its from-source install hurts today. That is a legitimate reason; it is not
the same reason, and the sibling comment in `bottles.yml` says so.

**What a bottle does NOT fix for Dreame, and the bigger prize:** its formula's caveats warn that
the first RUN builds `sunxi-fel` from source, needing a compiler and network. That happens at run
time, so no bottle can carry it. Moving that build into the formula's `install` block would put
`sunxi-fel` inside the bottle and remove the warning entirely — a real user-visible win, and a
formula change rather than a packaging one. Deliberately not bundled into "add bottles".

**Both now carry the same sharp edge**, which is the cost of this mechanism: a bottle is not
reproducible, so rebuilding one without re-running the block refresh leaves the tap advertising
checksums for files that no longer exist — and `brew install` then fails outright for everyone,
rather than falling back to source. That is why `tap-bottles.yml` is dispatchable in both repos and
why `bottle-block.py` refuses a partial set.

## The rc sweep — converged onto one shared script, and it is the one that deletes

`packaging/prune-rcs.sh` is now **vendored**, like the tap updater beside it. It was the last release
script each project still owned a private copy of, and the only one whose job is deletion: rc
releases, git tags, and the apt/dnf packages still being served for them, across all three
registries.

The two copies had converged on **what** to delete and diverged on **how to be sure it worked**, and
each held a guard the other lacked:

| | Whiskerless's copy | Dreame's copy |
|---|---|---|
| Enumerated | releases **and git tags**, so an orphan tag left by a half-finished sweep was found | releases only — an orphan tag was named nowhere and survived forever |
| Confirmed removal | trusted the DELETE status | re-read the live list and git refs, retried for eventual consistency |
| On failure | `set -e` and a non-zero exit, which reddens a release that already published | reported and exited 0 |
| Credentials | every token required up front | only the package token |
| Default | dry run unless `DRY_RUN=false` | deleted unless `--dry-run` was passed |

The shared script takes the safer half of every row. That last one mattered most: two call sites had
to start passing `DRY_RUN=false` explicitly, because a sweep that deletes when nobody said not to is
the one bug whose blast radius is every candidate on every registry.

**A published RELEASE never proves a published PACKAGE**, and both copies already knew it: the
registry upload is a separate step, so a stable can exist on all three hosts while its `.deb` and
`.rpm` never reached the repository. Deleting the candidate then leaves an apt subscriber with no
installable version — worse than the leftover the sweep exists to remove. The candidate must be
replaced in the same distribution and the same architecture, read off the published index, because
that is the only thing a user's package manager ever sees.

**Coverage was one-sided too, which is how the drift survived.** Dreame's copy carried a stubbed
integration suite; whiskerless's had no test at all. The suite now lives in
`tests/release/prune-rcs.sh` against a mutable fake registry, so a DELETE changes what the next GET
returns and the verification is exercised rather than mocked. Both projects run it.

**Coverage was one-sided at the call sites too.** Every prune test in both projects read
`publish.yml`; nothing in either test tree referenced the manual `prune-rcs.yml` at all. So the
automatic path — already fenced in by a stable-tag gate and six `needs:` — was pinned, while the
manual path — a human aiming a registry-wide delete with nothing upstream of it — was pinned by
nothing. That is how the two call sites drifted: dreame's manual dispatch had copied the shape of
its own `publish.yml` and swallowed a non-zero exit into a `::warning::`, so a failed sweep reported
success to whoever dispatched it.

**The call sites now differ on purpose.** `publish.yml` swallows a failure, because by the time it
runs the stable is published on all three registries and reddening the release sends somebody
hunting a publishing failure that did not happen. `prune-rcs.yml` does **not** swallow one, because
nothing is being released there. Reading one call site and "fixing" the other to match is the
obvious wrong move, so both projects pin the manual path in
`test_the_manual_prune_dispatch_cannot_delete_by_accident_or_report_a_failure_as_success`.

That guard **allowlists the whole job** rather than probing it. The key set is compared whole at
workflow, job and step level, so anything unlisted — `container`, `defaults`, `env`, `if`, `shell`,
`continue-on-error`, `permissions`, `strategy` — fails without the test naming it. Within that shape:
`workflow_dispatch` is the only trigger and `dry_run` its only input, `runs-on` is pinned by value,
the checkout is `actions/checkout` at a full commit with inputs exactly `{ref: main}`, and the sweep
is exactly `bash packaging/prune-rcs.sh` with an environment of exactly the four tokens,
`DRY_RUN: ${{ inputs.dry_run }}` and `STRICT: "true"`.

The allowlist is the point, because every blacklist here is incompletable, and each item below is a
mutation the guard is verified against rather than a hypothetical. `||`, `; true`,
`if ! cmd; then ... fi`, a pipeline, `set +e` and a custom `shell:` all turn a failed sweep green.
First-match probing accepts a second checkout of the dispatch ref beside a compliant one, silently
replacing the tree the reviewed script runs from. `ref: main` says nothing about *whose* main until
`repository:` is excluded too, and `@main` or `@v7` reintroduces a moving target. A
`${{ !inputs.dry_run }}` binding inverts the safe default while still naming the input. A job- or
step-level `BASH_ENV` is sourced by the shell before the pinned command ever runs. A swapped secret
keeps the key set intact while sending a credential to the wrong host, and the read failure that
follows is one the script deliberately survives.

**`STRICT` is what makes that exit status mean something, and the two callers set it differently on
purpose.** The script's own view is that a sweep either finished or stopped; how a stop is *reported*
is the caller's call. `publish.yml` leaves `STRICT` unset, because it runs once a stable is already
published on all three registries and a non-zero exit there reddens a release that succeeded.
`prune-rcs.yml` sets `STRICT: "true"`, because nothing is being released and the operator who pressed
Run needs the status to mean the sweep worked.

It parses **fail-safe** — anything but an exact `"true"` is non-strict — which is deliberately the
mirror of `DRY_RUN`'s fail-closed parse. `DRY_RUN` guards deletion, so ambiguity must mean "preview";
`STRICT` guards only reporting, so ambiguity must mean "stay quiet" rather than start reddening
published releases. A forge input passed through unevaluated is a case in the suite for both.

Three outcomes owe the operator a non-zero answer, and a counter of failures alone names only the
first two: tags **deleted but not verified gone** (residue), a sweep that **stopped early** on a
partial picture, and candidates **kept because a package index would not answer**. That last one is
the quiet one — nothing was deleted and no release was wrong, so it looks like a clean run, but the
sweep could not establish that a stable replaces the candidate in apt/dnf. It is counted separately
from residue precisely because nothing was deleted, and separately from an ordinary keep because a
sweep that could not see is not a sweep that found nothing to do.

It is decided **per candidate, at the keep site** — not per failed lookup. A candidate is undetermined
only when *every* reason it was kept was an unanswered question; one definite reason (the stable is
provably absent from a distribution) settles the outcome by itself, and an unreadable index sitting
beside it changed nothing. Counting per lookup instead would redden sweeps whose decision was never
in doubt, and a guard that fires when the answer was certain is one an operator learns to skip.

Even under `STRICT`, green certifies only that the sweep ran to completion with all three counters at
zero — never that any particular rc was removed, so the log remains the real report.

**And one limit no test in the tree can reach.** `workflow_dispatch` runs the workflow definition
belonging to the ref it was dispatched from; the pinned checkout replaces the working tree only
afterwards. So the guard binds *main's* copy of `prune-rcs.yml`, and dispatching an older ref runs
that ref's copy — its own swallow, its own checkout, its own inputs. The pin decides which **script**
runs, never which **workflow** does. Branches predating the pin stay dispatchable until they are
deleted, which is why the operational half of this guarantee is not letting stale release branches
linger in the forge.

## The formula's checksum marker — two spellings, on purpose

`render-formula.sh` substitutes `REPLACE_SDIST_SHA256` **and** `REPLACE_TARBALL_SHA256` with the same
value, and each project's templates use only one of them. That is not drift left in shared code: the
two describe the archive each project actually publishes, a PyPI sdist for whiskerless and a
byte-reproducible source tarball for dreame-valetudo, and both names are accurate for their own
formula. One renderer serves both, and its leftover-marker guard still fails a template that used
neither.

The consequence for anything reading a template is that **the marker has to be read out of the file,
never assumed**. A test that hardcodes one spelling silently becomes a no-op for the other project,
which is how a shared assertion can pass against a template it never touched.

## Secret input — converged on the guarantee, different in form

A command line is world-readable through `ps` for as long as the command runs, so neither project
lets a secret arrive that way. **Both hold that line; the mechanism differs because the secrets do.**

| | Whiskerless | Dreame Valetudo |
|---|---|---|
| The secret | the wifi password, typed by a person | the miio key + the rooted image's root password |
| Out-of-argv route | `--wifi-pass-file`, `$WHISKERLESS_WIFI_PASSWORD`, or a TTY prompt | streamed over **stdin** (`stdin_path=`, `push.py`, `rekey.py`) |
| Argv route exists? | yes — `--wifi-pass`, kept because it is documented and scripted against, and it warns once when used | no |
| Scrubbed from logs | yes | yes (`log.py` redacts the password and the dust token) |

Whiskerless offers the private routes first and warns when the public one is used anyway. Dreame
never exposes an argv route at all, because its secrets are produced by the tool rather than typed
by a person — there is no flag to deprecate. A `--*-file` flag there would create an input that
does not exist, which is ceremony, not convergence.

This was previously recorded as a capability Dreame lacked entirely. That was wrong: it was read
off a probe written in whiskerless's spelling, and Dreame's stdin route is the stronger of the two
(a file can be read by anyone who can read the path; the pipe cannot). The probe now matches the
guarantee rather than one project's flag names.

## Recorded capability variances

`tools/capability-diff.py` probes each project for a capability and reports any difference. A
difference is acceptable only when it is named **here, verbatim**, so that silencing one is a
deliberate act rather than a side effect of prose elsewhere in this file.

**`standalone linux binary`** — whiskerless publishes a single executable as a release asset;
dreame-valetudo publishes its onedir bundle packed as a tarball. The guarantee is shared (download
one thing, extract if needed, run it) and the artifact shape differs because the freeze does. Fully
reasoned under *PyInstaller onefile vs onedir*.

**`package/staging parity`** — dreame-valetudo verifies that the tree inside its `.deb`/`.rpm` is
byte-for-byte the tree that was built, and whiskerless does not. This is the artifact shape again,
not a missing check. Dreame packages `type: tree` entries, and a tree that loses one member still
installs, still reports its version, and still passes a host smoke, then fails in whichever phase
first reads what is gone. Whiskerless packages four individually enumerated files, so a missing one
is an nfpm error rather than a quiet omission, and its package smoke installs the real `.deb` and
`.rpm` and then RUNS the binary — which for a PyInstaller onefile exercises the entire archive,
because a truncated or altered one does not start. Same guarantee, reached by the means each
artifact shape allows.

## The update nudge — converged on asking the channel you are actually on

Both projects nudge when a newer release exists, and both now pick the endpoint BY CHANNEL: a stable
install asks `/releases/latest`, a candidate asks `/releases?per_page=10` and takes the newest tag it
serves. Both cache per channel too, with the channel recorded inside the entry as well as in the
filename — whiskerless in `.update-check` / `.update-check-rc`, dreame in `.update_check` /
`.update_check_rc`, each following its own file-naming habit.

`/releases/latest` **excludes prereleases**, so dreame previously could not tell a machine on an rc
about a newer rc: the candidate channel was invisible to exactly the users who opted into it, which
is the one group the nudge is most useful to. The port carried the CONDITION, not just the endpoint.
Pointing every install at the enumerating URL would have fixed the candidate channel by offering
stable users a prerelease their upgrade command cannot install — the opposite defect, and a louder
one. Both halves are pinned by tests in both projects.

The per-channel marker is the second half of the same fix, and the two have to land together. A
stable and a candidate install share one home, and dreame's single marker recorded no channel and
checked none. That was harmless only because every install asked `/releases/latest`: the marker could
never hold anything but a stable tag, so there was nothing dangerous to leak across. Adding the
candidate endpoint is what creates the exposure — now an rc's answer can sit in a marker a stable
install reads, and it will offer a prerelease its upgrade command cannot install, without a network
call in sight. Whiskerless met the other half of it: it validated the channel while keeping one file,
so a mismatch was rejected and refetched, and every switch paid the full timeout the daily cache
exists to avoid. One marker per channel, with the channel recorded inside it, closes both.

The trap this laid for the port, and the reason it is worth recording: the marker name is derived
from `__version__`, and the prerelease gate stamps an rc BEFORE running the suite. Four dreame tests
spelled `.update_check` literally, so they passed on every branch and would have failed the one run
that cuts a release. Both suites are now verified green under a properly stamped rc, and the tests
that name a marker say which channel they mean.

## The privacy guards — the MAC half converged, the serial half cannot

Both repos gate their tree against committed hardware addresses, with the same matcher:
colon, hyphen, Cisco-dotted and `bytes.fromhex` spellings, six-group runs judged by whole
token so an IPv6 address is not mistaken for one, and a run containing an approved fixture
taken to be that fixture.

whiskerless additionally gates **serials**, and dreame-valetudo deliberately does not. This
is not drift. An LR4 serial has a fixed shape — `LR4C` and six digits — that a pattern can
recognise, and it is unusually sensitive there because it doubles as the MQTT client-id and
both topic segments. A Dreame serial is `[A-Za-z0-9][A-Za-z0-9._-]{5,63}`: almost any token,
so the same guard would match ordinary prose on every run. A test that always fails is a test
somebody deletes, which would leave the repo worse off than having none.

If Dreame serials ever gain a recognisable prefix, this becomes convergeable and should be
revisited. Until then the MAC guard is the whole of what transfers.

## Still open, and NOT justified

**None.** Everything above is closed.

The most recent closure was the package matrix's distro depth, described at the end of this section.
Before it came the update nudge, recorded above, and before that openSUSE, which the cold audit
reported as a version disagreement — one project pinned
Leap 15.6, the other 16.0. It was not that. Each tested openSUSE at a different STAGE for a different
purpose, so neither had the other's coverage: dreame never installed its published `.rpm` on openSUSE
at all, and whiskerless only ever tested a compatibility target. Both now run the same `zypper` and
`zypper-floor` channels, on the same two images, against the published `.rpm` — the floor/current
pair the deb and rpm channels already used.

The openSUSE fix turned out to be one instance of a wider shape, and the rest of it stayed open for
a while afterwards. Dreame published one `.deb` and one `.rpm` for every distro in the family but
installed each on exactly one host — Debian 13 and Rocky 9 — so the `.rpm` never touched Fedora or
the Rocky 8 floor, and the `.deb` never touched a current Ubuntu. Whiskerless added all three on
2026-08-20, and its channel list names the digests as the ones "dreame-valetudo qualifies against":
dreame did qualify against those images, in its pre-merge matrix, building from source.
Nothing installed the artifact it actually ships. Dreame now runs `deb-file-ubuntu`,
`rpm-file-floor` and `rpm-file-fedora` beside the channels it already had.

A later sweep of the whole ladder — every family, floor against current — found three more of the
same shape. Rocky 10 had been the current release of the RPM family for a while and neither project
installed the shipped `.rpm` on it: dreame built against it pre-merge, whiskerless did not pin it at
all. Fedora's dnf5 is a reimplementation rather than a new version, parsing `.repo` files and
enforcing `gpgcheck` in its own code, so the Rocky 9 dnf4 leg proved nothing about the client a
current-Fedora subscriber actually gets. Both now run `rpm-file-current` and `dnf5-repo`. The third
was an architecture rather than a distro: dreame poured the bottle on amd64 only, on the stated
reasoning that the linuxbrew image had no arm64 build. It has one, and whiskerless had been pouring
on both arches for as long as the channel existed.

The same sweep found the images themselves carrying two Renovate identities. Dreame annotated Debian
12 and Ubuntu 22.04 as `-floor` where every other annotation in both projects called them `-compat`,
which meant one image answered to two depNames under two separate clamps that were free to drift
apart. One identity per image now, and the duplicate rules are gone.

What is still uneven is the pre-merge distro matrix, which dreame has and whiskerless does not; that
is a difference in where breadth is bought, not a gap in what ships. Both projects install-test
every channel they publish, on the same images, from the published artifact.

This section is meant to stay empty. A gap recorded here is a promise to close it, not a place to
retire one.
