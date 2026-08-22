# project-standard

The shared conventions and vendored tooling behind [`whiskerless`](https://github.com/SisyphusMD/whiskerless)
and [`dreame-valetudo`](https://github.com/SisyphusMD/dreame-valetudo).

- **[`CONVENTIONS.md`](CONVENTIONS.md)** — the rules both projects follow.
- **[`VARIANCE.md`](VARIANCE.md)** — the differences that are deliberate. Anything not in here is drift.
- **`shared/`** — the files that are literally the same in both projects.
- **`tools/`** — vendor them in, and check they have not been edited in place.

## How this works

Shared files are **vendored** — physically copied and committed into each consumer, with
`STANDARD.lock` recording the source tag and every file's SHA-256.

There is deliberately **no submodule, no runtime fetch, and no cross-repo package.** A three-year-old
tag of either project must still build and release with this repository unreachable. That is the only
reason a shared standard is safe here, and it is worth more than any convenience a live dependency
would buy.

```bash
# Update a consumer to the current standard
python3 tools/vendor.py ../whiskerless
python3 tools/vendor.py ../dreame-valetudo

# What a consumer runs in CI (stdlib only, no network)
python3 tools/check.py .
```

## The one rule that makes it work

**Never improve a shared helper by editing the vendored copy.** Change it here, re-vendor **both**
projects, land them together.

`tools/check.py` fails when a copy is edited in place, which is precisely the failure that drove
these two projects apart: someone improves a helper in one repo, the sibling never learns about it,
and a year later there are four divergent behaviours across two files that started identical.

A worked example — `changelog-section.sh` had drifted into two versions, each better in ways the
other was not:

| From | Improvement the sibling was missing |
|---|---|
| Dreame | fails loudly when the version heading is absent, instead of emitting empty release notes |
| Dreame | stops at any `## ` heading, not only bracketed ones |
| Whisk | strips the leading blank line |
| Whisk | stops at link-reference definitions, which a Keep a Changelog file collects at the foot |

Four improvements, two from each side, in a twenty-line script with no project-specific content.

## Testing the standard itself

```bash
./tests/test-release-common.sh
```

Network-free. Covers the guards that must hold *before* any request goes out — chiefly the tag
validator, whose output is interpolated straight into URL paths, so it refuses traversal
(`../../etc/passwd`), injection (`v0.2.0;rm -rf /`), whitespace and malformed versions. Also pins the
safe defaults: `REL_REPLACE_POLICY=immutable`, every request profile time-bounded, and mutations
never retried.

## Per-project parameters

`packaging/project.env` holds each project's own values and is **not** vendored or locked — it is the
parameter file, not shared content.

```bash
PROJECT_REPO_SLUG="SisyphusMD/whiskerless"
```

## Adding a file to the standard

1. It must be genuinely project-agnostic, or parameterised through `project.env`.
2. Merge the **union** of both projects' versions — assume each side knows something the other does
   not, because so far each side always has.
3. Test it against both repos' real data before vendoring.
4. Re-vendor both, land together.
