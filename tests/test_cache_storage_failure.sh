#!/usr/bin/env bash
set -euo pipefail

compose=(docker compose -f docker-compose.yml -f docker-compose.cache-readonly.yml)
tmp_dir="$(mktemp -d)"
cleanup() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

NGINX_CACHE_VALIDITY=10m NGINX_HOST_PORT=18080 "${compose[@]}" up --build -d nginx origin

base_url="http://127.0.0.1:18080"
ready=0
for attempt in $(seq 1 30); do
  if curl -fsS "$base_url/healthz" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" = "1"

curl -fsS -D "$tmp_dir/first.headers" -o "$tmp_dir/first.png" "$base_url/77x77/sample.png"
grep -qi '^X-Cache-Status: MISS' "$tmp_dir/first.headers"

curl -fsS -D "$tmp_dir/second.headers" -o "$tmp_dir/second.png" "$base_url/77x77/sample.png"
grep -qi '^X-Cache-Status: MISS' "$tmp_dir/second.headers"
cmp "$tmp_dir/first.png" "$tmp_dir/second.png"

python3 - "$tmp_dir/first.png" <<'PY'
import struct
import sys
data = open(sys.argv[1], "rb").read()
assert data[:8] == bytes.fromhex("89504e470d0a1a0a"), "response is not PNG"
width, height = struct.unpack(">II", data[16:24])
assert (width, height) == (77, 57), f"unexpected dimensions: {width}x{height}"
print(f"cache-write failure preserved origin response: {width}x{height}, two MISS responses")
PY

"${compose[@]}" logs --no-color nginx > "$tmp_dir/nginx.log"
grep -Eiq 'Read-only file system|Permission denied' "$tmp_dir/nginx.log"
