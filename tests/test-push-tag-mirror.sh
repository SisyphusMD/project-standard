#!/usr/bin/env bash
# Network-free tests for push-tag.sh's mirror confirmation.
#
#   tests/test-push-tag-mirror.sh
#
# The mirror check is three-state on purpose — arrived, definitively absent, unknown — and the
# unknown case is the one that regresses silently, because a check that cannot answer must not
# read as a confirmed failure. These stub curl and sleep to pin all three states, and to pin
# that the MUTATING sync is sent exactly once however long the read-only polling runs.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then echo "  ok   $1"; pass=$((pass + 1))
  else echo "  FAIL $1 (expected $2, got $3)"; fail=$((fail + 1)); fi
}

# Runs the mirror block from push-tag.sh with curl and sleep stubbed. $1 is the HTTP code the
# ref lookup should answer with; POSTs are counted in $posts.
# `posts` is created by the CALLER, not here: this function runs inside $(...), so a variable
# it assigns dies with the subshell and the count silently reads empty.
posts=$(mktemp)

run_mirror_block() {
  local code="$1" script
  script=$(sed -n '/^mirror_has_tag()/,/^done$/p' shared/packaging/push-tag.sh)
  : > "$posts"
  REF_CODE="$code" POSTS="$posts" bash -c '
    set -uo pipefail
    tag=v1.2.3
    token=stub
    GITHUB_SERVER_URL=https://forge.invalid
    GITHUB_REPOSITORY=owner/repo
    PROJECT_REPO_SLUG=owner/repo
    sleep() { :; }                       # no real waiting
    curl() {
      case "$*" in
        *push_mirrors-sync*) echo x >> "$POSTS"; return 0 ;;
        *) printf "%s" "$REF_CODE"; return 0 ;;
      esac
    }
    export -f curl sleep
    '"$script"'
  ' 2>&1
}

out=$(run_mirror_block 200)
check "200 confirms the tag"            "yes" "$(echo "$out" | grep -q 'confirmed on the mirror' && echo yes || echo no)"
check "200 sends exactly one sync POST" "1"   "$(wc -l < "$posts" | tr -d ' ')"

out=$(run_mirror_block 404)
check "404 reports not-yet, then gives up" "yes" "$(echo "$out" | grep -q 'never reached the mirror' && echo yes || echo no)"
check "404 still sends only one sync POST" "1" "$(wc -l < "$posts" | tr -d ' ')"

out=$(run_mirror_block 503)
check "5xx is unknown, not failure"     "yes" "$(echo "$out" | grep -q 'could not determine' && echo yes || echo no)"
check "5xx does not claim failure"      "no"  "$(echo "$out" | grep -q 'never reached the mirror' && echo yes || echo no)"

echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
