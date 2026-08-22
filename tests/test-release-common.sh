#!/usr/bin/env bash
# Network-free tests for the shared release library.
#
#   tests/test-release-common.sh
#
# Only the guards that must hold before any network call are covered here: the tag validator (whose
# output goes straight into URL paths), the replace policy default, and the timeout profiles. The
# asset state machine needs a real forge and is exercised against one during a release.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=shared/packaging/release-common.sh
. shared/packaging/release-common.sh

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then
    echo "  ok   $1"; pass=$((pass + 1))
  else
    echo "  FAIL $1 (expected $2, got $3)"; fail=$((fail + 1))
  fi
}

echo "rel_validate_tag accepts the two shapes a release workflow can cut"
for good in v0.2.0 v1.0.0 v0.2.0-rc.1 v10.20.30-rc.99; do
  rel_validate_tag "$good" 2>/dev/null; rc=$?
  check "accepts $good" 0 "$rc"
done

echo "rel_validate_tag refuses everything else, BEFORE the tag reaches a URL path"
while IFS= read -r bad; do
  rel_validate_tag "$bad" 2>/dev/null; rc=$?
  label=$(printf %s "$bad" | tr '\n' '~')
  check "refuses '$label'" 1 "$rc"
done <<'BAD'
0.2.0
v0.2
v0.2.0-rc1
v0.2.0-beta.1
v0.2.0 
latest
v0.2.0;rm -rf /
../../etc/passwd
v0.2.0/../v9.9.9
$(id)
BAD
rel_validate_tag "" 2>/dev/null; rc=$?
check "refuses an empty tag" 1 "$rc"

echo "GitHub asset-name normalisation — the rule that has no other symptom than a failed release"
# GitHub rewrites `~` to `.` in the STORED name and enforces uniqueness on the rewritten form. A
# project whose artifact filenames carry a native package version hits this on EVERY .deb and .rpm.
# BOTH projects do now — dreame's used to be version-free, which made it immune by accident, and
# that accident is exactly what made the missing version look harmless. The .pkg and the tarball
# stay unchanged because no packaging system normalises their version, so both spellings are pinned
# here together: the rule is "match what the packager reports", not "replace every tilde".
for case in \
  "whiskerless_0.2.0~rc.35_amd64.deb|whiskerless_0.2.0.rc.35_amd64.deb" \
  "whiskerless-0.2.0~rc.35.x86_64.rpm|whiskerless-0.2.0.rc.35.x86_64.rpm" \
  "dreame-valetudo_amd64.deb|dreame-valetudo_amd64.deb" \
  "dreame-valetudo-0.3.0-rc.16.tar.gz|dreame-valetudo-0.3.0-rc.16.tar.gz" \
  "dreame-valetudo_0.3.0~rc.17_amd64.deb|dreame-valetudo_0.3.0.rc.17_amd64.deb" \
  "dreame-valetudo_0.3.0~rc.17_arm64.deb|dreame-valetudo_0.3.0.rc.17_arm64.deb" \
  "dreame-valetudo-0.3.0~rc.17.x86_64.rpm|dreame-valetudo-0.3.0.rc.17.x86_64.rpm" \
  "dreame-valetudo-0.3.0~rc.17.aarch64.rpm|dreame-valetudo-0.3.0.rc.17.aarch64.rpm" \
  "dreame-valetudo-0.3.0-rc.17-macos-arm64.pkg|dreame-valetudo-0.3.0-rc.17-macos-arm64.pkg" \
  "a~b~c.deb|a.b.c.deb" \
  "plain.deb|plain.deb"; do
  raw="${case%%|*}"; want="${case##*|}"
  got=$(rel_github_asset_name "$raw")
  check "$raw -> $want" "$want" "$got"
done
# Idempotent: normalising an already-normalised name must not change it again.
once=$(rel_github_asset_name "whiskerless_0.2.0~rc.35_amd64.deb")
check "normalisation is idempotent" "$once" "$(rel_github_asset_name "$once")"

echo "publication defaults are the safe ones"
[ "$REL_REPLACE_POLICY" = immutable ]; check "REL_REPLACE_POLICY defaults to immutable" 0 $?

echo "every request profile is time-bounded, and mutations are not retried"
[[ "${REL_READ[*]}" == *--max-time* ]]; check "REL_READ is bounded" 0 $?
[[ "${REL_DOWNLOAD[*]}" == *--max-time* ]]; check "REL_DOWNLOAD is bounded" 0 $?
[[ "${REL_MUTATE[*]}" == *--max-time* ]]; check "REL_MUTATE is bounded" 0 $?
# A timed-out mutation may already have been applied; repeating it duplicates rather than recovers.
[[ "${REL_MUTATE[*]}" != *--retry* ]]; check "REL_MUTATE is NOT retried" 0 $?

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
