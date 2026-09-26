#!/usr/bin/env sh
# Point this repo's git at .githooks/ and make the hooks executable.
# Run once after cloning:   sh install-hooks.sh
set -e
cd "$(dirname "$0")"

# The guards must exist BEFORE the first commit, so initialise if needed.
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "no git repo here -- running git init first"
  git init -q .
fi

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push .githooks/commit-msg 2>/dev/null || true
echo "core.hooksPath -> .githooks"
echo ""
echo "Active guards:"
echo "  commit-msg  strips the two known trailers, blocks anything that survives"
echo "  pre-commit  blocks staged CONTENT carrying an attribution marker"
echo "  pre-push    blocks the push if any outgoing commit carries one, in"
echo "              content OR message -- the real boundary, since pre-commit"
echo "              can be skipped with --no-verify"
echo ""
echo "Verify with:  sh test-hooks.sh"
