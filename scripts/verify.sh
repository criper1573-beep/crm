#!/usr/bin/env bash
# Проверка FLOW CRM перед отчётом. Шага нет в репозитории — SKIP, не ошибка.
set -u
cd "$(dirname "$0")/.."

fail=0

say() {
  printf '%s\n' "$1"
}

# --- types ---
if git ls-files '*.ts' '*.tsx' '*.mts' '*.cts' | grep -q . || [ -f tsconfig.json ]; then
  if npx --no-install tsc --version >/dev/null 2>&1; then
    if npx --no-install tsc --noEmit; then
      say "PASS types — tsc --noEmit"
    else
      say "FAIL types — tsc --noEmit завершился с ошибкой"
      fail=1
    fi
  else
    say "FAIL types — есть TypeScript, локальный tsc не установлен (глобально не ставим)"
    fail=1
  fi
else
  say "SKIP types — нет TypeScript: нет tsconfig.json и отслеживаемых .ts/.tsx"
fi

# --- lint ---
has_lint_script=0
if [ -f package.json ] && python3 -c 'import json; raise SystemExit(0 if "lint" in json.load(open("package.json")).get("scripts", {}) else 1)'; then
  has_lint_script=1
fi
if [ "$has_lint_script" -eq 1 ] || [ -f ruff.toml ] || [ -f .ruff.toml ] || [ -f .flake8 ] || [ -f eslint.config.js ] || [ -f .eslintrc ] || [ -f .eslintrc.js ] || [ -f .eslintrc.json ]; then
  say "FAIL lint — конфиг линтера есть, но verify не знает, какой командой его запускать"
  fail=1
else
  say "SKIP lint — нет ruff, flake8, eslint и npm-скрипта lint"
fi

# --- tests ---
test_notes=""
test_bad=0
if git ls-files 'tests/*.py' | grep -q .; then
  if python3 -c 'import pytest' >/dev/null 2>&1; then
    py_out=$(python3 -m pytest -q --tb=line 2>&1) || py_status=$?
    py_status=${py_status:-0}
    py_summary=$(printf '%s\n' "$py_out" | tail -n 1)
    if [ "$py_status" -eq 0 ]; then
      test_notes="pytest: ${py_summary}"
    else
      test_bad=1
      say "FAIL tests — python3 -m pytest -q"
      printf '%s\n' "$py_out" | tail -n 30
    fi
  else
    test_bad=1
    say "FAIL tests — есть tests/*.py, модуль pytest не установлен"
  fi
else
  test_notes="python-тестов нет"
fi

if git ls-files 'tests/*.js' | grep -q .; then
  if command -v node >/dev/null 2>&1; then
    js_failed=0
    while IFS= read -r js; do
      if ! node "$js" >/tmp/verify-js.out 2>&1; then
        js_failed=1
        say "FAIL tests — node ${js}"
        tail -n 20 /tmp/verify-js.out
      fi
    done < <(git ls-files 'tests/*.js')
    if [ "$js_failed" -eq 0 ]; then
      test_notes="${test_notes:+${test_notes}; }node tests/*.js: exit 0"
    else
      test_bad=1
    fi
  else
    test_bad=1
    say "FAIL tests — есть tests/*.js, а node не найден"
  fi
fi

if [ "$test_bad" -eq 0 ]; then
  if [ -n "$test_notes" ]; then
    say "PASS tests — ${test_notes}"
  else
    say "SKIP tests — в репозитории нет unit-тестов"
  fi
else
  if [ -n "$test_notes" ]; then
    say "FAIL tests — часть прошла: ${test_notes}"
  fi
  fail=1
fi

# --- build ---
if [ -f package.json ] && python3 -c 'import json; raise SystemExit(0 if "build" in json.load(open("package.json")).get("scripts", {}) else 1)'; then
  say "FAIL build — npm-скрипт build есть, verify его не запускает, чтобы не тянуть сборку молча"
  fail=1
else
  say "SKIP build — сборки нет: статический frontend и Python без компиляции"
fi

# --- secrets (только отслеживаемые файлы, значения не печатаем) ---
secret_hits=$(mktemp)
scan_secret() {
  local kind="$1"
  local regex="$2"
  local tmp
  tmp=$(mktemp)
  git grep -n -I -E -e "$regex" -- . >"$tmp" 2>/dev/null || true
  if [ -s "$tmp" ]; then
    sed -E "s/^([^:]*:[0-9]+):.*/\1 ${kind}/" "$tmp" >>"$secret_hits"
  fi
  rm -f "$tmp"
}
scan_secret "sk-" 'sk-[A-Za-z0-9]{8,}'
scan_secret "ghp_" 'ghp_[A-Za-z0-9]+'
scan_secret "private-key" 'BEGIN PRIVATE'" KEY"
scan_secret "connection-string" '(postgres|postgresql|mysql|mongodb(\+srv)?|redis)://[^[:space:]/:@]+:[^[:space:]@]+@'
if [ -s "$secret_hits" ]; then
  say "FAIL secrets — совпадения в отслеживаемых файлах, значения скрыты:"
  cat "$secret_hits"
  fail=1
else
  say "PASS secrets — в отслеживаемых файлах нет sk-, ghp_, BEGIN PRIVATE KEY и пароля в строке подключения"
fi
rm -f "$secret_hits" /tmp/verify-js.out

if [ "$fail" -eq 0 ]; then
  say "OVERALL PASS"
else
  say "OVERALL FAIL"
fi
exit "$fail"
