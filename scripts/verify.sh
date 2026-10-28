#!/usr/bin/env bash
# The whole verification gate, in one command (§19).
#
#   ./scripts/verify.sh              # everything, seeded demo mode
#   ./scripts/verify.sh --postgres   # the same, plus the persistence tests against
#                                    # $DATABASE_URL (or the URL below)
#
# Backend tests need the project's virtualenv on PYTHONPATH: the packages are installed
# there, while the source tree is what is under test. Doing it here means nobody has to
# remember, and a missing dependency fails loudly instead of skipping a suite.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${SYMBIO_VENV:-$ROOT/venv}"
EXTRA_PYTEST_ARGS=()

if [[ "${1:-}" == "--postgres" ]]; then
  shift
  URL="${DATABASE_URL:-${SYMBIO_TEST_DATABASE_URL:-}}"
  if [[ -z "$URL" ]]; then
    echo "verify: --postgres needs DATABASE_URL (or SYMBIO_TEST_DATABASE_URL)" >&2
    exit 2
  fi
  EXTRA_PYTEST_ARGS+=("--symbio-postgres-url=$URL")
fi

status=0
note() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mFAILED:\033[0m %s\n' "$1"; status=1; }

note "backend: pytest"
if [[ -d "$VENV/lib" ]]; then
  PYPP="$(ls -d "$VENV"/lib/python*/site-packages 2>/dev/null | head -1)"
else
  PYPP=""
fi
(
  cd "$ROOT/backend" || exit 1
  PYTHONPATH="${PYPP}:${PYPP:+:}${ROOT}/backend" python3 -m pytest -q "${EXTRA_PYTEST_ARGS[@]}"
) || fail "pytest"

note "frontend: typecheck"
(
  cd "$ROOT/frontend" || exit 1
  node node_modules/typescript/bin/tsc --noEmit
) || fail "tsc --noEmit"

note "frontend: palette guard"
(
  cd "$ROOT/frontend" || exit 1
  npm run --silent lint:palette
) || fail "lint:palette"

note "frontend: production build"
(
  cd "$ROOT/frontend" || exit 1
  rm -rf .next
  npm run --silent build
) || fail "next build"

note "result"
if [[ $status -eq 0 ]]; then
  printf 'all gates passed\n'
else
  printf 'one or more gates failed\n'
fi
exit $status
