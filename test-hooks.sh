#!/usr/bin/env sh
# Proves the attribution guards actually block. Builds a throwaway repo in a
# temp dir, installs these hooks into it, and checks each layer both ways:
# it must REFUSE a marker and must ALLOW clean content.
#
# A guard that has never been shown to fail closed is not a guard.
#
#   sh test-hooks.sh      -> exits 0 only if every case behaves correctly

set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
TMP="${TMPDIR:-/tmp}/cdd-hook-test.$$"
PASS=0
FAIL=0

ok()   { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; }

cleanup() { cd /; rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$TMP"
cd "$TMP"
git init -q .
git config user.name  "Hook Test"
git config user.email "test@example.invalid"
git config commit.gpgsign false
mkdir -p .githooks
cp "$SRC/.githooks/pre-commit" "$SRC/.githooks/pre-push" \
   "$SRC/.githooks/commit-msg" "$SRC/.githooks/claude-markers.txt" .githooks/
chmod +x .githooks/pre-commit .githooks/pre-push .githooks/commit-msg
git config core.hooksPath .githooks

echo ""
echo "=== 1. pre-commit must BLOCK a marker in file content ==="
printf 'hello\n\nGenerated with [Claude Code]\n' > tainted.md
git add tainted.md
if git commit -q -m "add tainted file" >/dev/null 2>&1; then
  bad "pre-commit allowed a file containing 'Generated with [Claude Code]'"
else
  ok "pre-commit refused tainted file content"
fi

echo ""
echo "=== 2. pre-commit must BLOCK a session URL ==="
git reset -q
printf 'see https://claude.ai/code/session_abc123 for details\n' > tainted2.md
git add tainted2.md
if git commit -q -m "add session url" >/dev/null 2>&1; then
  bad "pre-commit allowed a claude.ai/code/session URL"
else
  ok "pre-commit refused a session URL"
fi

echo ""
echo "=== 3. pre-commit must ALLOW clean content that mentions vendors ==="
git reset -q
rm -f tainted.md tainted2.md
cat > clean.md <<'INNER'
# Notes
This paper cites Anthropic, OpenAI and Claude as AI vendors in its
bibliography. That is legitimate prose and must not be blocked.
INNER
git add clean.md
if git commit -q -m "add clean file" >/dev/null 2>&1; then
  ok "pre-commit allowed prose mentioning Claude/Anthropic (no false positive)"
else
  bad "pre-commit blocked legitimate vendor prose -- guard is unusable"
fi

echo ""
echo "=== 4. commit-msg must STRIP the two known trailers ==="
echo "second" >> clean.md
git add clean.md
git commit -q -m "real subject

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_zzz" >/dev/null 2>&1 || true
got=$(git log -1 --format=%B | tr -d '\r')
if printf '%s' "$got" | grep -qiE 'claude'; then
  bad "commit-msg left a Claude trailer in the message: $got"
else
  ok "commit-msg stripped both trailers (message now: '$(printf '%s' "$got" | head -1)')"
fi

echo ""
echo "=== 5. pre-push must BLOCK content already committed via --no-verify ==="
printf 'oops\nCo-Authored-By: Claude <noreply@anthropic.com>\n' > sneaky.md
git add sneaky.md
git commit -q --no-verify -m "snuck past pre-commit" >/dev/null 2>&1
git init -q --bare "$TMP/remote.git"
git remote add origin "$TMP/remote.git"
if git push -q origin HEAD:refs/heads/main >/dev/null 2>&1; then
  bad "pre-push allowed a --no-verify commit carrying a marker"
else
  ok "pre-push refused a commit that bypassed pre-commit"
fi

echo ""
echo "=== 6. pre-push must ALLOW a clean history ==="
git rm -q --cached sneaky.md >/dev/null 2>&1 || true
rm -f sneaky.md
git commit -q --no-verify -m "remove sneaky" >/dev/null 2>&1 || true
# rebuild a clean branch so no offending commit is in the pushed range
git checkout -q --orphan cleanbranch
git rm -rq --cached . >/dev/null 2>&1 || true
rm -f sneaky.md tainted.md tainted2.md 2>/dev/null || true
echo "clean only" > ok.md
git add ok.md
git commit -q -m "clean history" >/dev/null 2>&1
if git push -q origin cleanbranch:refs/heads/clean >/dev/null 2>&1; then
  ok "pre-push allowed a clean history"
else
  bad "pre-push blocked a clean history -- guard is too aggressive"
fi

echo ""
echo "=== 7. override must work and be logged ==="
printf 'Co-Authored-By: Claude <noreply@anthropic.com>\n' > ovr.md
git add ovr.md
if CLAUDE_GUARD_OVERRIDE=1 git commit -q -m "deliberate override" >/dev/null 2>&1; then
  if [ -f .git/claude-guard-override.log ]; then
    ok "override allowed the commit AND wrote .git/claude-guard-override.log"
  else
    bad "override allowed the commit but wrote no log"
  fi
else
  bad "override did not work"
fi

echo ""
echo "=== 8. BOOTSTRAP: the real repo must be able to commit AND push ITSELF ==="
# The guard files and this test script necessarily contain marker strings. If the
# allowlist is wrong, the repo cannot publish itself -- which is the one failure
# mode that would only surface at the moment of the first real push.
BOOT="$TMP/boot"
mkdir -p "$BOOT"
( cd "$SRC" && tar cf - --exclude=.git . ) | ( cd "$BOOT" && tar xf - )
cd "$BOOT"
git init -q .
git config user.name "Bootstrap Test"
git config user.email "boot@example.invalid"
git config commit.gpgsign false
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push .githooks/commit-msg 2>/dev/null || true
git add -A
if git commit -q -m "CDD audit: data, codebook and recompute script" >/dev/null 2>&1; then
  git init -q --bare "$TMP/bootremote.git"
  git remote add origin "$TMP/bootremote.git"
  if git push -q origin HEAD:refs/heads/main >/dev/null 2>&1; then
    ok "the repo can commit AND push itself (allowlist is correct)"
  else
    bad "pre-push blocked the repo from pushing itself -- allowlist incomplete"
  fi
else
  bad "pre-commit blocked the repo from committing itself -- allowlist incomplete"
fi
cd "$TMP"

echo ""
echo "========================================"
echo "  passed: $PASS   failed: $FAIL"
echo "========================================"
[ "$FAIL" -eq 0 ] || exit 1
echo "  all guards behave correctly."
