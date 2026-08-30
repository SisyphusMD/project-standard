#!/usr/bin/env bash
# shellcheck disable=SC2016
# Every single-quoted '$' below is a PATTERN this test matches against other
# scripts, never an expansion that was forgotten.
# Every GitHub call in the release path must carry a credential.
#
#   tests/test-github-auth.sh
#
# Unauthenticated github.com allows 60 requests an hour PER IP, and every runner, mirror probe and
# CI poller shares one. A script whose token is optional does not fail when that budget is gone: it
# answers 403, and a check built on it stops deciding anything while still reporting success.
#
# So the rule is stronger than "pass a token when you have one". The variable a file interpolates
# into its Authorization header must be MANDATORY, and the file must abort when it is absent —
# checked against the header's OWN variable, since every script already has some `${1:?usage}`
# argument assertion that would otherwise satisfy a looser reading.
#
# What this cannot prove is that a credential is non-empty at RUN time: `-H "$(registry_auth github)"`
# looks identical whether that function returns a token or an empty string. The mandatory-token
# assertions cover that case, which is why both halves exist.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then echo "  ok   $1"; pass=$((pass + 1))
  else echo "  FAIL $1 (expected $2, got $3)"; fail=$((fail + 1)); fi
}

# Is $2 mandatory in file $1? Either asserted directly, or assigned from an expansion that is.
# `${VAR:?}` and `${1:?}` are the only forms that abort instead of substituting an empty credential.
is_required() {
  grep -qE "\\\$\{$2:\?" "$1" && return 0
  grep -qE "^[[:space:]]*$2=\"?\\\$\{[A-Za-z0-9_]+:\?" "$1" && return 0
  return 1
}

touched=0
for f in shared/packaging/*.sh; do
  grep -qE 'api\.github\.com|uploads\.github\.com' "$f" || continue
  touched=$((touched + 1))
  name=$(basename "$f")

  # Only the schemes the GitHub API accepts. `Basic` is git's own http.extraheader, which these
  # scripts use against FORGEJO — a different host with no rate limit and its own credential.
  vars=$(grep -oE 'Authorization: (Bearer|token) \$\{?[A-Za-z_][A-Za-z0-9_]*' "$f" \
         | sed -E 's/.*\$\{?//' | sort -u)

  for v in $vars; do
    got=no; is_required "$f" "$v" && got=yes
    check "$name requires \$$v rather than defaulting it empty" "yes" "$got"
  done

  # A direct header is not proof the GITHUB credential was checked. prune-rcs.sh builds its GitHub
  # auth indirectly through registry_auth() while carrying an unrelated direct PACKAGE_TOKEN
  # header, so following header variables alone would confirm the wrong credential and pass while
  # $GH_TOKEN went unvalidated. Every recognised GitHub token the file MENTIONS must be mandatory,
  # whichever way it reaches the request.
  named=$(grep -oE '\b(GH_TOKEN|GH_REPO_READ_PAT|MIRROR_CI_TOKEN|GITHUB_ASSET_TOKEN)\b' "$f" | sort -u)
  for v in $named; do
    got=no; is_required "$f" "$v" && got=yes
    check "$name requires \$$v wherever it reaches the request" "yes" "$got"
  done

  check "$name authenticates its GitHub calls at all" \
        "yes" "$([ -n "$vars$named" ] && echo yes || echo no)"

  # The checks above prove a credential is required SOMEWHERE in the file. On their own they would
  # still pass if the Authorization header were deleted from the GitHub request itself, because a
  # sibling call to a different host (push-tag.sh also talks to Forgejo) keeps supplying a name to
  # follow. So look at the request itself.
  #
  # Both ends are reached through one level of indirection, and following neither would skip most
  # of these files: the URL is usually built into a variable (`API="https://api.github.com/..."`),
  # and the credential is often a prepared header or array (`-H "$PKG_AUTH"`, `"${auth[@]}"`).
  # Continuations are joined first — wrapped across lines, a URL and its header read as unrelated
  # statements.
  joined=$(sed -e ':x' -e '/\\$/{N;s/\\\n//;bx' -e '}' "$f")

  # Variables this file assigns a github.com URL to, so `curl "$API/..."` is recognised as GitHub.
  gh_vars=$(printf '%s\n' "$joined" \
            | grep -oE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=.*(api|uploads)\.github\.com' \
            | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/' | sort -u)
  gh_ref='(api|uploads)\.github\.com'
  for v in $gh_vars; do gh_ref="$gh_ref|\\\$\{?$v\b"; done

  # The hosts these scripts ALSO talk to, and any variable built from one. prune-rcs.sh assigns
  # `url="$REG/debian/..."` inside a case arm and then curls "$url", so exempting the host name
  # alone would still leave a package-registry request looking like an unauthenticated GitHub one.
  hosts='REG|FORGE|fj_url|CLUSTER_HOST|NAS_HOST|PKG_API|GITHUB_SERVER_URL'
  other_vars=$(printf '%s\n' "$joined" \
               | grep -oE "[A-Za-z_][A-Za-z0-9_]*=\"?\\\$\{?($hosts)\b" \
               | sed -E 's/=.*//' | sort -u)
  not_github="\\\$\{?($hosts)\b"
  for v in $other_vars; do not_github="$not_github|\\\$\{?$v\b"; done

  # A credential on the command is a literal Authorization header, or a variable this file assigns
  # one to. Matching the NAME alone is not enough: `auth=(-H "Accept: ...")` is still called `auth`
  # with no credential in it, so follow the name to its assignment and require the header there.
  unauth=0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    # The header written out in full needs no following.
    case "$line" in *Authorization*) continue ;; esac

    ok=0
    # Produced by a helper whose name says what it returns: -H "$(registry_auth "$registry")".
    # Anchored to the CALL: a looser "contains $( and auth" matches `"$(curl … "${auth[@]}"…)"`
    # itself, exempting every command that merely passes an auth array.
    printf '%s' "$line" | grep -qE '\$\([A-Za-z_]*[Aa]uth[A-Za-z_]*[[:space:])]' && ok=1

    # Otherwise follow each variable on the command to its assignment and require the header there.
    if [ "$ok" = 0 ]; then
      for v in $(printf '%s' "$line" | grep -oE '\$\{?[A-Za-z_][A-Za-z0-9_]*' | tr -d '${' | sort -u); do
        if grep -qE "^[[:space:]]*$v\+?=\(?.*Authorization" "$f"; then ok=1; break; fi
      done
    fi
    [ "$ok" = 1 ] || unauth=$((unauth + 1))
  # Every curl in these files is checked, not only ones naming a github.com URL: two reach GitHub
  # through a wrapper (`get "$API/..."` calling `curl "$1"`), which following the URL alone misses.
  #
  # Calls to the OTHER hosts these scripts talk to are exempt by name. That list is small and
  # explicit on purpose: an exemption someone must add deliberately beats a URL heuristic that
  # silently stops matching when a variable is renamed.
  done <<EOF
$(printf '%s\n' "$joined" | grep -vE '^[[:space:]]*#' | grep -E '(^|[^a-z_])curl ' \
  | grep -vE "$not_github")
EOF
  check "$name sends a credential on every GitHub request" "0" "$unauth"

  # A helper is accepted above by NAME, which says nothing about what it returns. Deleting the
  # `github)` arm from registry_auth leaves every other check green while the request goes out with
  # an empty header, so read the arm and require a GitHub credential in it.
  if grep -qE '^[A-Za-z_]*[Aa]uth[A-Za-z_]*\(\) \{' "$f"; then
    # No emptiness guard: an absent github arm IS the failure, not a reason to skip the check.
    arm=$(sed -n '/^[A-Za-z_]*[Aa]uth[A-Za-z_]*() {/,/^}/p' "$f" | grep -E '^[[:space:]]*github\)')
    got=no
    printf '%s' "$arm" | grep -qE 'GH_TOKEN|GH_REPO_READ_PAT|GITHUB_ASSET_TOKEN' && got=yes
    check "$name's auth helper returns a GitHub credential" "yes" "$got"
  fi

  # The conditional header is the specific shape that degrades silently: the request still goes
  # out, just without the credential. Requiring the variable above makes this redundant, so one
  # left behind means the fallback was reintroduced beside the requirement.
  optional=no
  grep -qE '\[ -[nz] "\$\{[A-Za-z_]+:-\}" \][[:space:]]*(&&|\|\|)[[:space:]]*auth' "$f" && optional=yes
  check "$name has no optional-credential fallback" "no" "$optional"
done

# Sourced libraries inherit their credential instead of building one. release-common.sh issues most
# of the actual GitHub requests but names no host, so the sweep above skips it. For a file that uses
# an auth array it never assigns, the invariant is simply that EVERY curl carries it.
for f in shared/packaging/*.sh; do
  grep -q '\${auth\[@\]}' "$f" || continue
  grep -qE '^[[:space:]]*(local )?auth\+?=' "$f" && continue    # builds its own; covered above
  name=$(basename "$f")
  bare=$(sed -e ':x' -e '/\\$/{N;s/\\\n//;bx' -e '}' "$f" \
         | grep -vE '^[[:space:]]*#' | grep -E '(^|[^a-z_])curl ' \
         | grep -cv '${auth\[@\]}')
  check "$name (inherits \$auth) passes it on every request" "0" "$bare"
done

check "the sweep actually inspected the GitHub callers" "yes" "$([ "$touched" -ge 5 ] && echo yes || echo no)"

echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
