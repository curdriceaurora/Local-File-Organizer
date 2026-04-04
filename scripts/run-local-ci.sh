#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

TASKS=()
RUN_INSTALL=true
PYTHON_BIN="${PYTHON:-python3}"
PYTHON_VERSIONS=("3.11.15" "3.12.13")
PYENV_ROOT_DIR="${PYENV_ROOT:-${HOME}/.pyenv}"
TMP_ROOT="${TMPDIR:-/tmp}"
VENV_ROOT="${TMP_ROOT%/}/local-file-organizer-ci"

print_usage() {
  cat <<'EOF'
Usage: scripts/run-local-ci.sh [task ...] [options]

Run the GitHub Actions checks locally on the current machine.

Tasks:
  quick         Install deps, run lint, type-check, docs link check, and PR CI tests
  lint          pre-commit run --all-files
  unused-deps   deptry src/
  type-check    mypy src/file_organizer/models/
  links         docs link-integrity check from ci.yml
  test          run non-benchmark CI tests on Python 3.11.15 and 3.12.13 in parallel
  test-full     run main-branch non-benchmark suite on Python 3.11.15 and 3.12.13 in parallel
  benchmark     run benchmark suite on Python 3.11.15 then 3.12.13 sequentially
  integration   integration coverage gate
  security      pip-audit and bandit
  all           quick + benchmark + integration + security

Options:
  --python BIN  Python executable to use for non-matrix tasks (default: python3)
  --no-install  Skip dependency installation
  --list        Show task list and exit
  --help        Show this help and exit

Notes:
  - This mirrors the current Linux CI jobs in .github/workflows/ci.yml.
  - Test matrix versions are pinned to the current GitHub Actions Ubuntu 24.04
    setup-python tool cache: Python 3.11.15 and 3.12.13.
  - It does not emulate GitHub-only pieces like CodeQL upload, Codecov upload,
    PR permissions, or the macOS/Windows hosted matrix from ci-full.yml.
EOF
}

print_task_list() {
  cat <<'EOF'
Available tasks:
  quick
  lint
  unused-deps
  type-check
  links
  test
  test-full
  benchmark
  integration
  security
  all
EOF
}

run_step() {
  local label="$1"
  shift

  echo ""
  echo "==> $label"
  "$@"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

resolve_pyenv_python() {
  local version="$1"

  if ! command -v pyenv >/dev/null 2>&1; then
    echo "Missing required command: pyenv" >&2
    echo "Install pyenv and the exact runner versions first:" >&2
    printf '  pyenv install %s\n' "${PYTHON_VERSIONS[@]}" >&2
    exit 1
  fi

  local pybin
  pybin="$(PYENV_VERSION="$version" pyenv which python 2>/dev/null || true)"
  if [[ -z "$pybin" || ! -x "$pybin" ]]; then
    echo "Python $version is not available via pyenv." >&2
    echo "Install it with: pyenv install $version" >&2
    exit 1
  fi

  printf '%s\n' "$pybin"
}

matrix_venv_dir() {
  local version="$1"
  printf '%s/py%s' "$VENV_ROOT" "${version//./-}"
}

ensure_matrix_venv() {
  local version="$1"
  local pybin
  pybin="$(resolve_pyenv_python "$version")"

  local venv_dir
  venv_dir="$(matrix_venv_dir "$version")"

  if [[ ! -x "$venv_dir/bin/python" ]]; then
    run_step "Create venv for Python $version" "$pybin" -m venv "$venv_dir"
  fi

  if $RUN_INSTALL; then
    run_step "Upgrade pip for Python $version" "$venv_dir/bin/python" -m pip install --upgrade pip
    run_step "Install deps for Python $version" "$venv_dir/bin/python" -m pip install -e ".[dev,search]"
    run_step "Install CI helper packages for Python $version" \
      "$venv_dir/bin/python" -m pip install faker pip-audit bandit[toml]
  fi
}

download_nltk_data() {
  local python_bin="${1:-$PYTHON_BIN}"
  run_step \
    "Download NLTK data" \
    "$python_bin" \
    -c \
    "import nltk; nltk.download('stopwords', quiet=True); nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True); nltk.download('wordnet', quiet=True)"
}

install_python_dependencies() {
  require_cmd "$PYTHON_BIN"
  run_step "Upgrade pip" "$PYTHON_BIN" -m pip install --upgrade pip
  run_step "Install Python dependencies" "$PYTHON_BIN" -m pip install -e ".[dev,search]"
  run_step "Install CI helper packages" "$PYTHON_BIN" -m pip install faker pip-audit bandit[toml]
}

run_in_matrix_parallel() {
  local label="$1"
  local fn_name="$2"
  shift 2

  local pids=()
  local versions=()

  for version in "${PYTHON_VERSIONS[@]}"; do
    (
      "$fn_name" "$version" "$@"
    ) &
    pids+=("$!")
    versions+=("$version")
  done

  local failed=0
  local idx
  for idx in "${!pids[@]}"; do
    if ! wait "${pids[$idx]}"; then
      echo ""
      echo "Task '$label' failed for Python ${versions[$idx]}."
      failed=1
    fi
  done

  if [[ $failed -ne 0 ]]; then
    exit 1
  fi
}

run_links_check() {
  run_step \
    "Check documentation links" \
    bash \
    -lc \
    '
      echo "Checking for broken documentation links..."
      links=$(grep -r -h "\[.*\](.*)" README.md docs/*.md 2>/dev/null | sed -E "s/.*\(([^)]+)\).*/\1/" | grep -E "^/" | sort -u)
      failed=0
      for link in $links; do
        if [[ "$link" == http* ]]; then
          continue
        fi
        filepath=${link%#*}
        if [[ ! -f "$filepath" ]]; then
          echo "Broken link: $link"
          failed=1
        fi
      done
      if [[ $failed -eq 1 ]]; then
        exit 1
      fi
      echo "All documentation links are valid"
    '
}

run_lint() {
  run_step "Run pre-commit" pre-commit run --all-files
}

run_unused_deps() {
  run_step "Run deptry" deptry src/
}

run_type_check() {
  run_step "Run mypy" mypy src/file_organizer/models/
}

run_test_pr_version() {
  local version="$1"
  local venv_dir
  venv_dir="$(matrix_venv_dir "$version")"

  run_step \
    "Verify pytest plugin imports (Python $version)" \
    "$venv_dir/bin/python" \
    -c \
    "import pytest_asyncio, faker; print('pytest-asyncio and faker loaded')"
  run_step \
    "Collect tests (Python $version)" \
    "$venv_dir/bin/pytest" \
    --collect-only \
    --quiet \
    --ignore=tests/e2e
  download_nltk_data "$venv_dir/bin/python"
  run_step \
    "Run PR CI test suite (Python $version)" \
    "$venv_dir/bin/pytest" \
    tests/ \
    -m \
    "ci and not benchmark" \
    --cov=file_organizer \
    --cov-report="xml:$venv_dir/coverage-pr.xml" \
    --timeout=30 \
    -n=auto \
    --override-ini=addopts=
}

run_test_pr() {
  local version
  for version in "${PYTHON_VERSIONS[@]}"; do
    ensure_matrix_venv "$version"
  done
  run_in_matrix_parallel "test" run_test_pr_version
}

run_test_full_version() {
  local version="$1"
  local venv_dir
  venv_dir="$(matrix_venv_dir "$version")"

  download_nltk_data "$venv_dir/bin/python"
  run_step \
    "Run main-branch CI test suite (Python $version)" \
    "$venv_dir/bin/pytest" \
    tests/ \
    -m \
    "not benchmark and not e2e" \
    --cov=file_organizer \
    --cov-fail-under=93 \
    --cov-report="xml:$venv_dir/coverage-full.xml" \
    --timeout=30 \
    -n=auto \
    --override-ini=addopts=
  run_step \
    "Run docstring coverage gate (Python $version)" \
    "$venv_dir/bin/interrogate" \
    -v \
    src/ \
    --fail-under \
    95
}

run_test_full() {
  local version
  for version in "${PYTHON_VERSIONS[@]}"; do
    ensure_matrix_venv "$version"
  done
  run_in_matrix_parallel "test-full" run_test_full_version
}

run_benchmark_version() {
  local version="$1"
  local venv_dir
  venv_dir="$(matrix_venv_dir "$version")"

  download_nltk_data "$venv_dir/bin/python"
  run_step \
    "Run benchmark suite (Python $version)" \
    "$venv_dir/bin/pytest" \
    tests/ \
    -m \
    benchmark \
    --benchmark-only \
    --strict-markers \
    --timeout=30 \
    --override-ini=addopts=
}

run_benchmark() {
  local version
  for version in "${PYTHON_VERSIONS[@]}"; do
    ensure_matrix_venv "$version"
  done
  for version in "${PYTHON_VERSIONS[@]}"; do
    run_benchmark_version "$version"
  done
}

run_integration() {
  download_nltk_data
  run_step \
    "Run integration coverage gate" \
    pytest \
    tests/ \
    -m \
    integration \
    --strict-markers \
    --cov=file_organizer \
    --cov-branch \
    --cov-fail-under=60 \
    --cov-report=term-missing \
    --cov-report=xml \
    --timeout=60 \
    --override-ini=addopts=
}

run_security() {
  run_step \
    "Run pip-audit" \
    bash \
    -lc \
    "$PYTHON_BIN -m pip install -e . >/dev/null && pip-audit -r <($PYTHON_BIN -m pip freeze)"
  run_step "Run bandit" bandit -r src/ -c pyproject.toml
}

expand_task() {
  local task="$1"
  case "$task" in
    quick)
      TASKS+=("lint" "unused-deps" "type-check" "links" "test")
      ;;
    all)
      TASKS+=(
        "lint"
        "unused-deps"
        "type-check"
        "links"
        "test"
        "benchmark"
        "integration"
        "security"
      )
      ;;
    lint|unused-deps|type-check|links|test|test-full|benchmark|integration|security)
      TASKS+=("$task")
      ;;
    *)
      echo "Unknown task: $task" >&2
      print_usage >&2
      exit 1
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --no-install)
      RUN_INSTALL=false
      shift
      ;;
    --list)
      print_task_list
      exit 0
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      expand_task "$1"
      shift
      ;;
  esac
done

if [[ ${#TASKS[@]} -eq 0 ]]; then
  TASKS=("quick")
fi

EXPANDED_TASKS=()
for task in "${TASKS[@]}"; do
  if [[ "$task" == "quick" ]]; then
    EXPANDED_TASKS+=("lint" "unused-deps" "type-check" "links" "test")
  else
    EXPANDED_TASKS+=("$task")
  fi
done
TASKS=("${EXPANDED_TASKS[@]}")

if $RUN_INSTALL; then
  install_python_dependencies
fi

echo "Running local CI tasks: ${TASKS[*]}"
echo "Pinned test matrix versions: ${PYTHON_VERSIONS[*]}"

for task in "${TASKS[@]}"; do
  case "$task" in
    lint)
      run_lint
      ;;
    unused-deps)
      run_unused_deps
      ;;
    type-check)
      run_type_check
      ;;
    links)
      run_links_check
      ;;
    test)
      run_test_pr
      ;;
    test-full)
      run_test_full
      ;;
    benchmark)
      run_benchmark
      ;;
    integration)
      run_integration
      ;;
    security)
      run_security
      ;;
  esac
done

echo ""
echo "Local CI completed successfully."
