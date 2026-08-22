# SisyphusMD project conventions

The shared standard for `whiskerless`, `dreame-valetudo`, and projects that follow them.

This is a working document, not a compliance regime. Every rule here exists because breaking it
already cost something in one of these repos. If a rule ever costs more than it saves, change it
here — not by quietly diverging in one project.

**Scope:** these conventions bind both projects. They do **not** demand identical code. Deliberate,
recorded differences live in [`VARIANCE.md`](VARIANCE.md); anything not recorded there is drift.

---

## 1. Python, typing, and code shape

| Topic | Convention | Permitted variance |
|---|---|---|
| **Language floor** | One literal minimum Python version, stated identically in packaging metadata, type-check config, lint config, CI, and docs. CI executes that **exact patch release**, not just its minor series. | A framework-specific job may need a newer interpreter, but it never raises the base contract silently. |
| **Formatting** | UTF-8, LF, final newline, no trailing whitespace, spaces. Four-space Python, two-space everything else. 100-column Python lines. | Generated and vendored files keep their upstream format. Markdown tables may exceed 100 columns where wrapping would hurt readability. |
| **Linting** | A shared Ruff baseline with explicit `target-version`. A rule is disabled only for a concrete incompatibility, never to silence a backlog. | Domain overlays differ: `ASYNC` only where async exists; BLE, subprocess, and packaging overlays may add rules. |
| **Type checking** | Exact-pinned mypy with `strict = true` and `warn_unreachable = true`. Pin it, because `strict` semantics move between releases. Type the test fixtures that expose recording objects rather than scattering `type: ignore`. | Being typed does not make an internal module a supported public API. |
| **Value objects** | Frozen, slotted dataclasses for identities, parsed protocol values, and immutable results. Anything advertised as immutable defensively copies caller input and makes nested collections immutable enough to prevent alias mutation — otherwise call it a shallow view and name it that way. | Mutable orchestration objects are right when they explicitly own effects or evolving session state. |
| **Parsing** | Parse untrusted bytes, archives, and persisted state **once**, at a defensive boundary, into typed values. Preserve unknown/raw values — a future firmware will add them. Pure decisions consume typed values, not scattered strings or marker filenames. | Disk and wire encodings stay project-specific and backward-compatible. |
| **Effects** | Environment, console, clock, sleep, subprocess/device runner, and persistence sit behind an explicit context or narrow injectable seam. Pure validation, planning, and transition decisions stay separate from effects. | Async vs synchronous internals — see `VARIANCE.md`. |
| **Errors** | Project-owned typed exceptions wherever callers or recovery behaviour differ; always `raise ... from exc`. Expected operational failures reach **one** CLI error funnel. Programmer faults stay visible under `--debug`. | A consumed library curates a public exception hierarchy; a CLI-only application may keep narrower internal types. |
| **Module size** | Split at stable semantic boundaries — parse/dispatch, persistence/migration, pure planning vs effects. Characterise behaviour with tests first. Line count is a signal, never a reason on its own. | Do not split an ordered flash sequence or a transport loop just to make two repos look symmetrical. |

## 2. Naming, imports, and public surfaces

Use domain names that distinguish concepts instead of reusing a convenient generic noun. The shared
vocabulary:

- **`DeviceProfile`** — static supported-device capabilities.
- **`RobotRecord`** / **`SavedRobot`** — a mutable persisted installation record.
- **`RobotIdentity`** — serial, model, or config value used to verify the physical robot.
- **`State`** / **`Snapshot`** — a typed observation at a point in time, never an on-disk profile.
- **`Plan`** / **`Decision`** / **`Transition`** — pure output describing effects without performing them.

Rules:

- Keep stable public names compatible. A clearer name for a public symbol or CLI verb ships with a
  documented alias and deprecation window, plus an installed-artifact compatibility test.
- Prefer explicit project-package imports. No import-time I/O, no mutable module globals used to
  communicate between phases, no wildcard imports, no accidental re-export of internals.
- Public library exports are listed deliberately in `__all__`. Ship `py.typed` only alongside an
  explicit compatibility promise.
- `snake_case` functions, `PascalCase` types, `UPPER_SNAKE_CASE` constants. Predicates read as
  questions: `is_`, `has_`, `can_`, `supports_`.

## 3. Comments

Comment the non-obvious **why** — the invariant, the constraint, the consequence, the recovery
requirement. Never narrate what the code plainly does.

- Earn every line. Tighten verbose comments; never strip load-bearing *why* just because it is long.
- No changelog or war stories: not "was N of M", not "the old regex…", not "added for issue #12".
  That belongs in the commit message. Historical reasoning that must survive goes in a dated note,
  linked from a short current-invariant comment.
- No cryptic labels without context ("Option C:").
- **A comment that contradicts the code, or another comment in the same file, is a defect.** Both
  repos have shipped these. Examples found and fixed: a docstring pointing at a function that does
  not exist; a module docstring declaring "one secret lives here" three lines above "two kinds of
  secret live here"; a Windows accommodation asserting "the store holds no secrets" in a file whose
  own docstring lists the CA private key.
- Leave vendored and upstream-copied boilerplate as-is. Do not tidy it into divergence.

## 4. DRY, and what "shared" means

1. Remove duplication when two paths share the same **invariant and failure semantics** — not merely
   similar-looking code.
2. Keep product protocols, state machines, hardware sequences, retry timing, and framework adapters
   project-local. Do not force MQTT register writes and Home Assistant state writes into one helper
   when their verification and pacing differ.
3. Genuinely shared, project-agnostic code lives in **`SisyphusMD/project-standard`** and is
   **vendored** — physically committed — into each consumer, with `STANDARD.lock` recording the
   source tag and per-file SHA-256.
4. **No submodule, no runtime fetch, no cross-repo package.** An old tag must still build and release
   offline, years later, with the standard repository unreachable. This constraint is not negotiable;
   it is the only reason a shared standard is safe.
5. Never improve a shared helper by editing the vendored copy. Change it in the standard, re-vendor
   **both** projects, land them together. `tools/check.py` fails CI when a copy is edited in place —
   that is the mechanism, and editing around it defeats the entire arrangement.
6. `packaging/project.env` holds each project's parameters and is deliberately outside the lock.

## 5. Tests

| Layer | Convention |
|---|---|
| **Pure unit** | Table-test parsers, codecs, reducers, preconditions, migration decisions, and version ordering with no real effects. Prove unknown values round-trip and that caller-owned input cannot mutate a snapshot. |
| **Effect seam** | Recording runners, scripted consoles, fake clocks, fake MQTT/BLE links, controlled filesystems. Assert **exact** argv, transcript, wire bytes, call order — and **zero calls** on denial. |
| **Public behaviour** | Exercise the real entry point: exit code, stdout/stderr, cancellation, `--debug`, and what state is retained versus deleted. Avoid tests coupled only to private details. |
| **Installed artifact** | Build the real wheel/package/bottle, install into a clean environment, run its declared entry points, then remove or upgrade it. Imports must not rely on the checkout being importable — that masks packaging failures. |
| **Published artifact** | Download from **every** promised origin and bind to the expected digest. One forge is never evidence for another. |
| **Physical hardware** | Record artifact digest, device model, firmware, scenario, and outcome. Evidence is for those exact bytes on that exact firmware — not for a differently-stamped rebuild. |

- Name tests for observable behaviour: `test_restore_rejects_duplicate_canonical_path_before_write`.
- Every bug fix carries the lowest practical regression that **fails on the parent commit**.
- Destructive-path denials assert exact negative postconditions, not just an error message.
- Randomness and time are injected or seeded. Network and hardware access are opt-in, named suites —
  an ordinary unit run never discovers and touches a live device.
- Coverage is branch-aware and risk-weighted. Measure before setting a floor. Require 100% on the
  narrow things that matter: final mutation guards, destructive preflight, error funnels, and runner
  seams. Do not impose an arbitrary repository-wide number in place of measuring.

## 6. Shell, packaging, and workflows

Every item below is a scar. Treat them as settled.

- Operational Bash: `#!/usr/bin/env bash`, `set -euo pipefail`, quote every expansion, validate
  targets explicitly, pass ShellCheck at `--severity=warning` under a **digest-pinned** image.
- **Bound every HTTP call.** An unreachable host otherwise hangs with no deadline and strands every
  step sequenced after it. Reads may retry; **mutations must not** — a timed-out write may already
  have applied, and repeating it duplicates rather than recovers.
- TLS verification is never disabled. `curl -k` with a credential attached is a credential handed to
  whoever is in the middle. There is no "it's my own server" exemption when the request crosses the
  public internet.
- Publication is **immutable**: same name, same bytes, forever. Identical bytes are an idempotent
  no-op; different bytes under an existing name are a hard failure needing a new tag. **Never delete
  an object to replace it** — that window is where a re-driven partial publish loses an artifact.
- A 2xx is the forge's word, not evidence. **Read back** every mutation and compare bytes.
- Look tags up with the **exact** endpoint. GitHub's plural `git/refs/tags/<tag>` is a *prefix*
  match: waiting for `v0.2.0` is satisfied by an existing `v0.2.0-rc.1`. Use singular `git/ref/`,
  and check the wait's result — an exhausted wait must fail closed, never fall through into creating
  a release that mints its own tag from the default branch.
- **GitHub rewrites `~` to `.` in stored asset names** and enforces uniqueness on the rewritten form;
  Forgejo stores names verbatim. Any project whose artifact filenames carry a native package version
  must normalise the name for lookup and upload while still comparing bytes against the local file.
- Coupled refs go up with `git push --atomic`, then get read back. Prefer
  `http.extraheader` over embedding a token in the remote URL.
- Build contexts are explicit allowlists. `.dockerignore` is defense in depth, not the boundary —
  `docker cp .` ignores it entirely. Keep signing material out of the build context and in a
  `mktemp` file with a cleanup trap, copied to its own path.
- Third-party actions are pinned to full commit SHAs with a readable version comment. **Keep the
  `# renovate:` marker beside every pin** — remove it and that pin silently stops being updated.
- Default workflow permissions read-only; write scope and secrets live on the consuming step only.
- Self-hosted and persistent runners execute **only trusted same-repository code**. Gate PR jobs on
  `github.event.pull_request.head.repo.full_name == github.repository`.
- CI runs the literal floor interpreter, a current one, static checks, tests, installed artifacts,
  and the declared platform matrix. Hand-maintained file lists get a discovery invariant so a new
  shipped file cannot silently escape lint or tests.

## 6a. Renovate postUpgradeTask scripts

A script Renovate runs on the update branch executes **inside Renovate's own container**, not your
CI image. That container is Node-based and carries none of your toolchain.

- No `python3`. No assuming GNU-only utility flags.
- Handle both checksum spellings: `sha256sum` on Linux runners, `shasum -a 256` on macOS.
- **Refuse to write a digest you could not fetch.** A pin invented after a failed download makes
  every later build verify against nothing. Note that a failed `curl` piped into a hasher still
  produces a *valid-looking* hash — the one for empty input — so the guard must be `pipefail` plus
  `set -e`, not a non-empty check on the result.
- **Read the pin back** after rewriting and fail if it did not take.

Both projects already do all of this. It is written down because it is the kind of knowledge that
lives in one repo's comments until the day someone writes a second script without it.

Deliberately **not** shared: the pin inventories themselves. Which pins exist and which files hold
them is genuinely project-specific — Whisk pins a CPython tarball checksum inside a workflow, Dreame
pins helper digests in `constants.py` and its Homebrew formulae. Factoring a fifteen-line helper out
from under those would buy nothing.

## 6b. Artifact filenames carry the NATIVE package version

Every published artifact carries its version in the filename, so two downloads in `~/Downloads` can
be told apart and the second does not silently overwrite the first.

**The spelling is whatever the packaging system itself reports — not the git tag.** These differ,
and the difference is deliberate rather than an inconsistency to "fix":

| Artifact | Tag `v0.3.0-rc.17` becomes | Because |
|---|---|---|
| `.deb` / `.rpm` | `0.3.0~rc.17` | nfpm normalises a semver prerelease to the `~` form; `dpkg -I` and `rpm -qi` report that, and a file must be named after what it contains |
| `.pkg` | `0.3.0-rc.17` | `pkgbuild --version` stores the string verbatim, so the tag form *is* the native form |
| source tarball | `0.3.0-rc.17` | no packaging system normalises it |

Derive the package form once, next to where the tag is read, and use that variable for filenames:

```bash
export VERSION="${GITHUB_REF_NAME#v}"   # the tag form, for nfpm and pkgbuild --version
PKGVER="${VERSION/-rc./~rc.}"           # the native form, for .deb/.rpm FILENAMES
```

Two consequences that are easy to miss, and both have bitten:

- **GitHub rewrites `~` to `.` in the stored asset name** and enforces uniqueness on the rewritten
  form; Forgejo stores it verbatim. Two consequences, and the second is the one that bites:
  - Never construct a GitHub asset URL from the local filename — go through
    `rel_github_asset_name()` in `shared/packaging/release-common.sh`.
  - **Never compare asset names across registries literally.** One asset answers to two spellings,
    so a literal comparison reports one asset as two — which reads as "ambiguous", not as "equal",
    and makes tooling *refuse* rather than fail loudly. Collapse to the canonical (`~`→`.`) form to
    compare, and keep the verbatim spelling as the name to upload. This is silent by construction:
    the release still goes green while cross-registry self-healing quietly stops.
- **Nothing may match these names literally.** Reconcile matches by *role* glob, the release
  completeness gate matches by *suffix*, and the README is stamped only on a stable release. A
  literal name in any of those is a latent break the next time the scheme moves — and a rename
  applied to the build step but not to the test/upload/gate steps breaks the release outright.

## 6c. A release gate must run on the RELEASE path

CI runs on a branch; a release is cut from a tag. A gate that lives only in `ci.yml` does not
constrain what a release may ship. Every non-regression gate — coverage, lint, type-check, the
version-of-record check — runs in `ci.yml` **and** in `release.yml` **and** in `prerelease.yml`.

## 6d. State the licence, and why it follows from who consumes you

Every project records its licence **and the reasoning** in `CONTRIBUTING.md`. Not the licence name —
the argument. Three questions, answered in order:

1. **Who consumes this?** Nobody (a standalone tool), other code (a library), or a network service.
2. **What does that make copyleft cost?** For a standalone tool, nothing. For a library imported
   into someone else's application, it reaches their combined work. For anything network-served,
   AGPL's section 13 reaches users who were never handed a copy.
3. **What does the ecosystem around it use?** A licence out of step with its neighbours is friction
   with no benefit, and can foreclose futures — an upstream that refuses copyleft dependencies is a
   door that closes on day one.

The two consumers of this standard answer differently and both are right: whiskerless is MIT because
Home Assistant imports it; dreame-valetudo is GPL-3.0 because nothing imports it. **A licence
difference between sibling projects is not drift** — but an *undocumented* one is, because the next
person cannot tell which it was.

Also record what third-party code ships alongside, and whether it is **linked** or merely
**executed**. Executing a GPL-2.0 binary as a separate process is aggregation and imposes nothing;
linking it is a combined work. That distinction decides whether a bundled helper is a non-issue or a
licence violation, and it is invisible from the file list.

## 6e. Name the surface you promise, and let a consumer prove it

Every project states, in `CONTRIBUTING.md`, exactly what it will not break — and everything not
named is explicitly free to change. Without that, every symbol is potentially load-bearing and
nothing can be refactored with confidence.

**The surface differs by who consumes you; the discipline does not.** A library that other code
imports promises names and types. An application nobody imports promises its CLI: subcommand names,
flags, exit codes, and any on-disk layout holding data a user cannot recreate. Both promise exit
codes, because both get scripted. Neither promises human-readable output text — a caller parsing
prose is depending on something that was never offered.

**Do not promise output text, and say so.** It is the difference between being able to improve a
message and being stuck with a typo forever.

**Enforce the promise against a real consumer, not against good intentions.** The failure mode is
not someone breaking a promised name — that gets caught. It is the promise staying small and true
while the actual consumed surface grows around it, so a rename that every check called safe breaks
a consumer the promise said did not exist. If you ship a consumer (a bundled integration, an
example, a smoke test), make a test assert that everything it imports is inside the promise. When
that test fails, the honest fixes are to widen the promise or make the consumer need less —
never to quietly keep reaching past it.

Changing a promised name means keeping the old spelling working, recording the deprecation in
`CHANGELOG.md`, and removing it no sooner than the next MINOR release. Additions need no window.

## 6f. A check that cannot be shown to fail is not evidence

Every convergence probe, invariant test and drift gate is run against a state where it MUST fail,
before it is trusted. Not as a nicety — four separate checks in this project passed while measuring
nothing:

- a probe matching `workflows/ci-pr.yml` in *file contents*, which matched the sentence in
  `CONTRIBUTING.md` describing the workflow, and reported both projects as having it while one had
  no such file;
- a probe matching `DEBIAN_FLOOR_IMAGE`, reporting install-matrix parity across a 44-stage-versus-
  5-stage difference;
- a test asserting the bundled consumer imports nothing unpromised, whose off-by-one in a module
  path split made it pass while two submodules leaked;
- a test asserting `pytest.raises(Die)` on an abort path, where the exit-0 subclass and the exit-1
  base both satisfy it, so the exit code it existed to pin was never checked.

Each looked like coverage and was decoration. The negative control is the cheap part: point the
check at the repository before the change, or delete the export it depends on, and watch it go red.
If it does not, the check is measuring a mention, a substring, or a superclass — not the thing.

**Corollary: prefer file existence or a call site to a substring.** "Does this word appear
somewhere" is the failure mode; "does this file exist" and "is this function actually called with
these arguments" cannot be satisfied by prose describing them.

## 7. Documentation, changelog, repository

- PEP 621 + Hatchling, `README.md`, `CHANGELOG.md`, SPDX license metadata, `LICENSE`, contribution
  guidance, security/support routing, machine-readable project URLs.
- Changelogs explicitly follow Keep a Changelog and SemVer and retain one `Unreleased` section.
- Documentation is journey-first: prerequisites, support status, install, first run, normal
  operation, update, candidate opt-in and return, backup and recovery, uninstall, troubleshooting.
  **Commands shown in a journey must be executable in that order on a clean system.**
- Generated facts have one source. Command names, channels, versions, package filenames, and support
  tiers render from manifests and are checked for drift. Do not duplicate a numeric threshold in
  prose when CI is authoritative.
- Recovery and uninstall text states exactly what is retained, deleted, reversible, and
  device-affecting.
- **Version-relative statements must say which version they are relative to.** "Returning to stable
  is a downgrade" is true while the candidate is ahead of the published stable and false afterwards.
  Write the condition, not just the conclusion.
- Ignore files are a safe union of virtual environments, build outputs, packages, signing material,
  platform metadata, and local tool state. They are not a security control.

## 7a. Documentation names the thing; it does not speak as "we"

Reference documentation is written in the third person. **Second person stays** — telling a reader
what *you* do is ordinary technical writing, and rewriting it into passive voice makes instructions
worse. This is about the first person only: "we", "our", "us".

The reason is not style. "our key" tells a reader nothing they can act on and quietly assumes they
know who "we" are; "the SisyphusMD signing key" names the thing, and a reader can go and look at it.

Two exceptions, both real:

- **Quoted program output stays verbatim.** A menu that reads `I already have one — I will give you
  the files` is the program speaking, and paraphrasing it in the docs means the docs no longer match
  the screen.
- **Some plurals are load-bearing.** Where a passage exists to distinguish *this* project's key
  from a third party's, deleting the possessive deletes the distinction. Rewrite to name both
  parties rather than to satisfy a grep — and never at the cost of epistemics: "on the unit we
  tested" becomes "on the one unit tested", which still says one unit, not "on tested units".

## 8. CLI and UX

- A bare invocation or empty state gives the user the **next valid action**. It must never recommend
  a command whose own preconditions reject the pristine state.
- Prompts state effect, target, what is retained or deleted, reversibility, and recovery, in
  proportion to risk. Destructive identity-changing operations require typed, target-specific
  confirmation; ordinary optional actions use a plain yes/no.
- **Never map an unrecognised input to a silent default.** `set <thing> enabled` must not quietly
  mean *off* because `enabled` was not in the accepted list. Unknown booleans, invalid numbers, and
  malformed times produce a concise typed error or a bounded re-prompt — never silent false, never a
  traceback.
- Every parse that can raise reaches the CLI error funnel. A mistyped time is a one-line message,
  not a stack trace.
- EOF and interruption cancel with **zero** new effects.
- Success prints only after the promised postcondition is observed or durable state is read back.
  Warnings precede the affected action. Partial progress names the completed boundary and the exact
  resume instruction.
- All output flows through an injectable console. Non-TTY and `NO_COLOR` output stays ordered,
  bounded, and semantically complete — colour and spinners never carry the only status meaning.
- **Bound what you print by output, not by input count.** Capping "the newest 3 changelog sections"
  does not bound anything when one section is 166 lines.
- Every subcommand has its own `--help`. Global usage in response to `cmd sub --help` is a bug.
- Error messages lead with the actionable problem, name the target safely, and give one concrete
  remedy. `--debug` adds the traceback with a privacy warning.

## 9. The sibling rule

Every improvement to one project is evaluated for the other. Not "considered eventually" — evaluated
in the same change, with one of four outcomes: **ported**, **ported with a project-specific
implementation**, **not applicable** (say why), or **deliberate variance** (record it in
`VARIANCE.md`).

The enforcement is one line in the pull request template:

> ☐ Sibling repo: ported / not applicable because …

"Not noticed" and "different project" are not answers. This costs a sentence per PR, which is why it
will actually happen — and it is the single rule that, had it existed, would have prevented most of
what the convergence audit found.

## 10. Lint codes in shared files

A vendored file carries **no `# noqa` directives naming a project's rule codes.** The two consumers
do not enable the same rule set, so a code one of them does not select reads as an unused directive
in that repo and fails `RUF100` — the suppression itself becomes the lint error.

Instead, the consumer whose rule set objects adds a `per-file-ignores` entry naming the vendored
path. The exemption belongs with the configuration that created the need for it.

Measured on the real repos: converging Whiskerless onto Dreame's rule set costs 12 `PLC0415`
findings in production code (deliberate lazy imports for optional heavy dependencies — keep them
ignored, they are an architectural choice, not a backlog) and **5 `PLW0603` findings, all of them
the migration globals in `profiles.py`.** That second one is worth having: it is a real design
defect that a converged lint config would have surfaced automatically.
