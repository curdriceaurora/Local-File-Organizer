#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# test-local-matrix.sh — Mirror ci-full.yml locally
#
# Runs the same Python version matrix that CI runs,
# using pyenv for Python version management.
#
# Prerequisites:
#   brew install pyenv           # macOS
#   pyenv install 3.9.21 3.10.16 3.11.11 3.12.8
#
# Usage:
#   ./scripts/test-local-matrix.sh           # Full matrix
#   ./scripts/test-local-matrix.sh --python  # Python matrix only (default)
#   ./scripts/test-local-matrix.sh --quick   # Fastest: Python 3.12 only
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PYTHON_VERSIONS=("3.9" "3.10" "3.11" "3.12")
FAILED=()
QUICK=false

# ── Parse arguments ──
for arg in "$@"; do
  case "$arg" in
    --python) ;;  # default behaviour, accepted for backwards compat
    --quick)  QUICK=true ;;
    --help|-h)
      echo "Usage: $0 [--python|--quick]"
      echo ""
      echo "  --python   Run Python matrix (default)"
      echo "  --quick    Run Python 3.12 only (fastest check)"
      echo ""
      echo "Prerequisites:"
      echo "  pyenv with Python 3.9, 3.10, 3.11, 3.12 installed"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg (try --help)"
      exit 1
      ;;
  esac
done

if $QUICK; then
  PYTHON_VERSIONS=("3.12")
fi

echo "Local CI Matrix — mirroring ci-full.yml"
echo "════════════════════════════════════════════════"
echo ""

# ── Check pyenv ──
if ! command -v pyenv >/dev/null 2>&1; then
  echo "❌ pyenv not found. Install it first:"
  echo "   brew install pyenv    # macOS"
  echo "   curl https://pyenv.run | bash  # Linux"
  exit 1
fi

# ── Python matrix ──
for version in "${PYTHON_VERSIONS[@]}"; do
  echo "══════════════════════════════════════"
  echo "  Python ${version}"
  echo "══════════════════════════════════════"

  # Resolve the pyenv Python binary for this version
  PYBIN="$(PYENV_VERSION="${version}" pyenv which python 2>/dev/null || true)"

  if [ -z "$PYBIN" ] || [ ! -x "$PYBIN" ]; then
    echo "⚠️  Python ${version} not installed — skipping"
    echo "   Install: pyenv install ${version}"
    echo ""
    FAILED+=("Python ${version}: not installed")
    continue
  fi

  VENV="/tmp/fo-test-py${version//./}"
  rm -rf "$VENV"

  echo "  Creating venv from $PYBIN..."
  "$PYBIN" -m venv "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"

  echo "  Installing dependencies..."
  pip install -e ".[dev]" -q 2>&1 | tail -1

  echo "  Running pytest..."
  if pytest "$REPO_ROOT/tests/" -m "not regression" --override-ini="addopts=" -q; then
    echo ""
    echo "  ✅ Python ${version} — PASSED"
  else
    echo ""
    echo "  ❌ Python ${version} — FAILED"
    FAILED+=("Python ${version}: test failures")
  fi

  deactivate
  rm -rf "$VENV"
  echo ""
done

# ── Summary ──
echo "══════════════════════════════════════"
echo "  Summary"
echo "══════════════════════════════════════"

if [ ${#FAILED[@]} -eq 0 ]; then
  echo "✅ All checks passed — safe to push"
  exit 0
else
  echo "❌ ${#FAILED[@]} failure(s):"
  for f in "${FAILED[@]}"; do
    echo "   • $f"
  done
  echo ""
  echo "Fix these before pushing to avoid CI failures."
  exit 1
fi
