#!/usr/bin/env bash
set -euo pipefail

script="tools/select_published_image_tag.sh"
check() {
  local ref=$1 expected=$2 actual
  actual="$("$script" "$ref")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: ref=%s expected=%s actual=%s\n' "$ref" "$expected" "$actual" >&2
    exit 1
  fi
  printf 'PASS: %s -> %s\n' "$ref" "$actual"
}

check main main
check feature/example main
check v1.2.3 1.2.3
check v1.2.3-rc.1 1.2.3-rc.1
check v1.2.3+build.7 1.2.3
check v1.2.3-rc.1+build.7 1.2.3-rc.1

if "$script" >/dev/null 2>&1; then
  echo "FAIL: missing argument unexpectedly succeeded" >&2
  exit 1
fi

echo "Published image tag normalization tests passed."
