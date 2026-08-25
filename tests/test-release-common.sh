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
# curl cannot tell a write that never landed from one that landed and lost its reply, so the retry
# lives in rel_upload_verified instead, where it can look before it writes.
[[ "${REL_MUTATE[*]}" != *--retry* ]]; check "REL_MUTATE is NOT retried at the curl layer" 0 $?

echo "rel_upload_verified retries writes, and the look-before-writing is what makes that safe"

# A connection that breaks AFTER the forge commits is indistinguishable from one that never landed.
# The re-check is what tells them apart, so the asset must not be sent a second time.
res=$(
  uploads=0; looks=0
  rel_asset_state() { looks=$((looks + 1)); [ "$looks" -ge 2 ] && return 0; return 10; }
  upload_asset() { uploads=$((uploads + 1)); return 1; }
  sleep() { :; }
  rel_upload_verified list name file LABEL >/dev/null 2>&1; rc=$?
  echo "$rc $uploads"
)
check "a write that already landed is recognised, not repeated" "0 1" "$res"

# The ordinary transient: the first attempt genuinely did not land, so writing again is the fix.
res=$(
  uploads=0
  rel_asset_state() { return 10; }
  rel_verify_uploaded_asset() { return 0; }
  upload_asset() { uploads=$((uploads + 1)); [ "$uploads" -ge 2 ]; }
  sleep() { :; }
  rel_upload_verified list name file LABEL >/dev/null 2>&1; rc=$?
  echo "$rc $uploads"
)
check "a write that did not land is retried until it does" "0 2" "$res"

# 11 is a verdict about the bytes. Retrying it would just re-lose the same race.
res=$(
  uploads=0
  rel_asset_state() { return 11; }
  upload_asset() { uploads=$((uploads + 1)); return 0; }
  sleep() { :; }
  rel_upload_verified list name file LABEL >/dev/null 2>&1; rc=$?
  echo "$rc $uploads"
)
check "a byte conflict ends the loop instead of retrying" "1 0" "$res"

# The one that matters most: 12 means the forge was never actually asked. Writing on an unanswered
# question is how an upload that already landed gets sent a second time.
res=$(
  uploads=0
  rel_asset_state() { return 12; }
  upload_asset() { uploads=$((uploads + 1)); return 0; }
  sleep() { :; }
  rel_upload_verified list name file LABEL >/dev/null 2>&1; rc=$?
  echo "$rc $uploads"
)
check "an unanswered state check never licenses a write" "1 0" "$res"

echo "a failed request is told apart from an unreadable one"

# Folding these together is what let a dropped connection read as a content conflict.
res=$(
  auth=()
  curl() { return 7; }
  rel_asset_state "http://example.invalid" name file >/dev/null 2>&1; echo $?
)
check "rel_asset_state reports a failed request as 12, not 1" 12 "$res"

# 12 says "we could not find out", which is never grounds to declare the upload lost.
res=$(
  tries=0
  rel_asset_state() { tries=$((tries + 1)); [ "$tries" -ge 3 ] && return 0; return 12; }
  sleep() { :; }
  rel_verify_uploaded_asset list name file >/dev/null 2>&1; rc=$?
  echo "$rc $tries"
)
check "rel_verify_uploaded_asset keeps looking after a 12" "0 3" "$res"

# A retried read must land in a file curl can truncate, not on a stdout it cannot rewind. Reading
# the body back from the -o path is what proves it went there.
res=$(
  auth=()
  curl() {
    local out=""
    while [ $# -gt 0 ]; do
      if [ "$1" = "-o" ]; then out=$2; shift 2; continue; fi
      shift
    done
    printf '{"ok":1}' > "$out"
  }
  rel_read_json "http://example.invalid"
)
check "rel_read_json reads the body from a truncatable file" '{"ok":1}' "$res"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
