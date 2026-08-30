#!/usr/bin/env bash
# Network-free tests for push-tag.sh's mirror confirmation.
#
#   tests/test-push-tag-mirror.sh
#
# The mirror check is three-state on purpose — arrived, definitively absent, unknown — and the
# unknown case is the one that regresses silently, because a check that cannot answer must not
# read as a confirmed failure. These stub curl, git and sleep to pin all three states, to pin that
# a tag serving the WRONG object is not mistaken for an arrival, and to pin that the MUTATING sync
# is sent exactly once however long the read-only polling runs.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then echo "  ok   $1"; pass=$((pass + 1))
  else echo "  FAIL $1 (expected $2, got $3)"; fail=$((fail + 1)); fi
}

# Runs the mirror block from push-tag.sh with curl, git and sleep stubbed. $1 is the HTTP code the
# ref lookup answers with, $2 the object SHA it serves; POSTs are counted in $posts.
# `posts` is created by the CALLER, not here: this function runs inside $(...), so a variable
# it assigns dies with the subshell and the count silently reads empty.
posts=$(mktemp)
PUSHED_SHA=1111111111111111111111111111111111111111

run_mirror_block() {
  local code="$1" served="$2" script
  # The token assertion lives above the push (so a missing one cannot leave a tag pushed), and
  # the mirror block below it. Take the two pieces and skip the push in between, so this exercises
  # the requirement without needing to stub git's network side.
  script="$(grep -m1 'GH_REPO_READ_PAT:?' shared/packaging/push-tag.sh)
$(sed -n '/^mirror_ref_json=/,/^done$/p' shared/packaging/push-tag.sh)"
  : > "$posts"
  REF_CODE="$code" SERVED_SHA="$served" WANT_SHA="$PUSHED_SHA" POSTS="$posts" \
  GH_REPO_READ_PAT="${TOKEN_OVERRIDE-stub-read-token}" bash -c '
    set -uo pipefail
    tag=v1.2.3
    token=stub
    GITHUB_SERVER_URL=https://forge.invalid
    GITHUB_REPOSITORY=owner/repo
    PROJECT_REPO_SLUG=owner/repo
    sleep() { :; }                       # no real waiting
    # Only rev-parse is reached here, and it must answer with the object the push produced.
    git() { case "$1" in rev-parse) printf "%s" "$WANT_SHA" ;; *) return 0 ;; esac; }
    curl() {
      local out="" prev=""
      for a in "$@"; do
        [ "$prev" = "-o" ] && out="$a"
        prev="$a"
      done
      case "$*" in
        *push_mirrors-sync*) echo x >> "$POSTS"; return 0 ;;
        *) [ -n "$out" ] && printf "{\"object\":{\"sha\":\"%s\"}}" "$SERVED_SHA" > "$out"
           printf "%s" "$REF_CODE"; return 0 ;;
      esac
    }
    export -f curl sleep git
    '"$script"'
  ' 2>&1
}

confirmed() { echo "$1" | grep -q 'confirmed on the mirror' && echo yes || echo no; }
gave_up()   { echo "$1" | grep -q 'never reached the mirror' && echo yes || echo no; }
unknown()   { echo "$1" | grep -q 'could not determine' && echo yes || echo no; }

out=$(run_mirror_block 200 "$PUSHED_SHA")
check "200 serving the pushed object confirms the tag" "yes" "$(confirmed "$out")"
check "200 sends exactly one sync POST"                "1"   "$(wc -l < "$posts" | tr -d ' ')"

# The case existence-only checking got wrong: a tag name is reusable, so a ref left behind by a
# partial prune answers 200 while still pointing at the previous release.
out=$(run_mirror_block 200 2222222222222222222222222222222222222222)
check "200 serving a STALE object is not an arrival"   "no"  "$(confirmed "$out")"
check "200 serving a stale object gives up"            "yes" "$(gave_up "$out")"

out=$(run_mirror_block 404 "")
check "404 reports not-yet, then gives up"             "yes" "$(gave_up "$out")"
check "404 still sends only one sync POST"             "1"   "$(wc -l < "$posts" | tr -d ' ')"

out=$(run_mirror_block 503 "")
check "5xx is unknown, not failure"                    "yes" "$(unknown "$out")"
check "5xx does not claim failure"                     "no"  "$(gave_up "$out")"

# The probe must never fall back to an unauthenticated request: github.com allows 60 an hour
# per IP and every runner shares one, so the fallback answers 403 and the check stops deciding.
out=$(TOKEN_OVERRIDE="" run_mirror_block 200 "$PUSHED_SHA")
check "an absent read token aborts rather than probing unauthenticated" "no" "$(confirmed "$out")"

# Where the guard sits is the point of it. Prepending the assertion to the extracted block above
# proves it aborts, not that it aborts BEFORE the refs are published — move it below the push and
# that check still passes while a missing token leaves the tag pushed and the job failed.
guard_line=$(grep -n 'GH_REPO_READ_PAT:?' shared/packaging/push-tag.sh | head -1 | cut -d: -f1)
push_line=$(grep -n 'push --atomic' shared/packaging/push-tag.sh | head -1 | cut -d: -f1)
check "the token guard precedes the push" "yes" \
      "$([ -n "$guard_line" ] && [ -n "$push_line" ] && [ "$guard_line" -lt "$push_line" ] && echo yes || echo no)"

echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
