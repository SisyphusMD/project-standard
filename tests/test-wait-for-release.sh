#!/usr/bin/env bash
# Network-free tests for which roles wait-for-release.sh demands of a release.
#
#   tests/test-wait-for-release.sh
#
# The script is sourced with WAIT_FOR_RELEASE_NO_POLL set, which stops it before the poll, against a
# scratch packaging/ holding a made-up role table. The tap, registry and GitHub checks need a real
# forge and are exercised against one during a release.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
root=$PWD

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then
    echo "  ok   $1"; pass=$((pass + 1))
  else
    echo "  FAIL $1 (expected '$2', got '$3')"; fail=$((fail + 1))
  fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp shared/packaging/wait-for-release.sh shared/packaging/release-common.sh "$work/"
printf '%s\n' 'PROJECT_REPO_SLUG="SisyphusMD/demo"' 'PROJECT_TAP_SLUG="SisyphusMD/homebrew-tap"' \
  > "$work/project.env"

# roles <asset-roles.sh body>: write the table the next source reads.
roles() { printf '%s\n' "$1" > "$work/asset-roles.sh"; }

# missing <asset names...>: what the wait would still be waiting for, in a fresh shell each time.
missing() {
  # $0 is the copied script, which is where it looks for its siblings.
  WAIT_FOR_RELEASE_NO_POLL=1 GITHUB_ASSET_TOKEN=unused bash -c '. "$0" v1.0.0 && missing_roles "$1"' \
    "$work/wait-for-release.sh" "$(printf '%s\n' "$@")"
}

# _IGNORED_ASSETS as every real project declares it: bash 3.2 aborts on it unbound under `set -u`.
TABLE="_ASSET_ROLES=('demo_*_amd64.deb' 'demo-*-macos-arm64.pkg' 'demo-*-macos-x86_64.pkg')
_IGNORED_ASSETS=('*.bottle.tar.gz' '*.bottle.json')"
BOTTLE='demo-1.0.0.arm64_sequoia.bottle.tar.gz'

echo "without a retired table every role is demanded"
roles "$TABLE"
check "the Intel .pkg is waited for" " demo-*-macos-x86_64.pkg" \
  "$(missing demo_1.0.0_amd64.deb demo-1.0.0-macos-arm64.pkg "$BOTTLE")"

echo "a retired role is never demanded, and nothing else relaxes"
roles "$TABLE
_RETIRED_ASSET_ROLES=('demo-*-macos-x86_64.pkg')"
# The exit status too: a script that aborted prints nothing either, which reads as complete.
out=$(missing demo_1.0.0_amd64.deb demo-1.0.0-macos-arm64.pkg "$BOTTLE"); rc=$?
check "complete without the Intel .pkg" "0:" "$rc:$out"
check "a live role is still waited for" " demo-*-macos-arm64.pkg" \
  "$(missing demo_1.0.0_amd64.deb "$BOTTLE")"
check "the bottle is still waited for" " *.bottle.tar.gz" \
  "$(missing demo_1.0.0_amd64.deb demo-1.0.0-macos-arm64.pkg)"

echo "a retired table that cannot mean what it says is refused"
roles "$TABLE
_RETIRED_ASSET_ROLES=('demo-*-macos-x86_64.pkgg')"
out=$(missing demo_1.0.0_amd64.deb 2>&1); rc=$?
check "a typo is not silently ignored" "2 refused" "$rc $(grep -q 'is not in _ASSET_ROLES' <<<"$out" && echo refused)"
roles "$TABLE
_OPTIONAL_ASSET_ROLES=('demo-*-macos-x86_64.pkg')
_RETIRED_ASSET_ROLES=('demo-*-macos-x86_64.pkg')"
out=$(missing demo_1.0.0_amd64.deb 2>&1); rc=$?
check "optional and retired at once" "2 refused" "$rc $(grep -q 'both optional and retired' <<<"$out" && echo refused)"

cd "$root" || exit 1
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
