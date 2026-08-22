# Adopting the standard

Order matters: commit the standard first, then vendor, then apply the migration patch, then wire CI.

## 1. Commit the standard

Stage by name (never `-A`), per house convention:

```
git add README.md CONVENTIONS.md VARIANCE.md pyproject.toml .gitignore shared tools migrations
git commit -m "feat: shared conventions, vendored tooling, and a drift lock for both projects"
git tag -a v0.1.0 -m "standard v0.1.0"
```

The tag matters: `vendor.py` records it in each consumer's `STANDARD.lock`, and an untagged working
tree records `(untagged working tree)` instead, which is useless for tracing later.

## 2. Vendor into each consumer

```
python3 tools/vendor.py ../whiskerless
python3 tools/vendor.py ../dreame-valetudo
```

Then write each project's parameter file — **not** vendored, deliberately outside the lock:

```
echo 'PROJECT_REPO_SLUG="SisyphusMD/whiskerless"'      > ../whiskerless/packaging/project.env
echo 'PROJECT_REPO_SLUG="SisyphusMD/dreame-valetudo"'  > ../dreame-valetudo/packaging/project.env
```

## 3. Apply the migration patch — ALREADY DONE, kept as a record

**Do not run this step against either current consumer.** Both adopted the standard long ago, so
the patches no longer apply to their heads and `git apply --check` fails — they do not name the
pre-adoption commits they were generated against, and those are what they need. They are kept
because they are the record of what adoption changed, and as the worked example for adopting a
THIRD project: regenerate against that project's own tree rather than replaying these.

Adoption was verified green in a scratch clone at the time: whiskerless **1085 passed**, dreame
**1728 passed**, both repos' own `ruff` clean, whiskerless `mypy` clean.

## 4. Wire the drift check into CI

Without this the lock is decoration. One step per repo, in the job that already runs Python.

**`whiskerless/.forgejo/workflows/ci.yml`**, in the `hygiene` job beside the existing
`Documentation links` step:

```yaml
      - name: Vendored standard has not drifted
        # A shared helper improved by editing the copy here never reaches the sibling project, which
        # is how these two drifted apart in the first place. Change it in project-standard,
        # re-vendor both, land together.
        run: python3 packaging/check-standard-sync.py
```

**`dreame-valetudo/.forgejo/workflows/ci.yml`**, in the `python` job after the lint/typecheck step:

```yaml
      - name: Vendored standard has not drifted
        run: python3 packaging/check-standard-sync.py
```

Optionally also enforce the ignore floor, which currently fails in **both** repos (whiskerless is
missing `*.p12` and `*.p8` while it notarises; dreame is missing `*.key`, `.DS_Store`, `htmlcov/`
and others):

```yaml
      - name: .gitignore contains the shared base
        run: python3 packaging/check-gitignore-base.py .
```

Fix the reported gaps before adding that step, or it lands red.

## 5. One decision before the release helpers go live

`REL_REPLACE_POLICY` defaults to `immutable`, which is right for everything reproducible. Whiskerless
deliberately keeps `bottles.yml` dispatchable so one failed platform can be rebuilt without cutting a
new candidate — and a bottle rebuild produces different bytes. If you want to keep that path, its
dispatch invocation needs `REL_REPLACE_POLICY=replace`; otherwise a failed bottle platform costs a
new RC tag. Nothing else should ever set it.
