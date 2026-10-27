#!/usr/bin/env bash
# Network-free test that revendor-standard.sh releases its output when it finishes.
#
#   tests/test-revendor-watchdog.sh
#
# The clone watchdog once orphaned its `sleep`, which inherited stdout, so anything reading the
# script's output (a pipe, Renovate's post-upgrade capture) waited out the whole clone deadline
# after the work was done. Nothing fails when that happens, it only stalls, so the time is the test.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/repo/packaging" "$tmp/bin"
cp shared/packaging/revendor-standard.sh "$tmp/repo/packaging/"
echo 'PROJECT_STANDARD="9.9.9"' > "$tmp/repo/packaging/release-pins.env"
echo '{"source_tag": "v0.0.1"}' > "$tmp/repo/STANDARD.lock"
# A clone that fails at once: the watchdog is armed and then torn down, which is the path at issue.
printf '#!/bin/sh\nexit 1\n' > "$tmp/bin/git"
chmod +x "$tmp/bin/git"

start=$(date +%s)
out="$(PATH="$tmp/bin:$PATH" REVENDOR_CLONE_SECONDS=30 bash "$tmp/repo/packaging/revendor-standard.sh" 2>&1 | cat)"
elapsed=$(( $(date +%s) - start ))

fail=0
case "$out" in
  *"failed or exceeded"*) echo "  ok   the failed clone is reported" ;;
  *) echo "  FAIL the failed clone is not reported: $out"; fail=1 ;;
esac
if [ "$elapsed" -lt 10 ]; then
  echo "  ok   the output closed ${elapsed}s after the clone ended"
else
  echo "  FAIL the output stayed open ${elapsed}s, so the watchdog outlived the clone"; fail=1
fi
exit "$fail"
