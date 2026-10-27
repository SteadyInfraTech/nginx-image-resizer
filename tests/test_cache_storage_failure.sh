#!/usr/bin/env bash
set -euo pipefail

tmp_dir="$(mktemp -d)"
cleanup() {
  docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT
on_error() {
  docker compose ps >&2 || true
  docker compose logs --no-color nginx origin >&2 || true
}
trap on_error ERR

NGINX_CACHE_VALIDITY=10m NGINX_CACHE_TMPFS_SIZE=512k NGINX_HOST_PORT=18080 docker compose up --build -d nginx origin

# NGINX /healthz only proves that the proxy process is running. The test is
# specifically about cache-write failures, so first ensure the upstream is
# serving valid images; otherwise startup races can produce unrelated 415s.
origin_ready=0
for attempt in $(seq 1 30); do
  if docker compose exec -T origin python -c 'from urllib.request import urlopen; r=urlopen("http://127.0.0.1:8081/sample.png", timeout=1); assert r.status == 200 and r.headers.get_content_type() == "image/png"; r.read(8)' >/dev/null 2>&1; then
    origin_ready=1
    break
  fi
  sleep 1
done
test "$origin_ready" = "1"

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

benchmark_status=0
python3 tools/benchmark.py --base-url "$base_url" --path /77x77/sample.png \
  --requests 2000 --concurrency 4 --timeout 15 --mode unique > "$tmp_dir/report.json" || benchmark_status=$?
cat "$tmp_dir/report.json"
test "$benchmark_status" -eq 0

python3 - "$tmp_dir/report.json" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
assert report["requests_completed"] == 2000, report
assert report["http_status_counts"] == {"200": 2000}, report
assert report["cache_status_counts"] == {"MISS": 2000}, report
assert not report["errors"], report
print("all 2,000 transformed responses succeeded despite cache storage pressure")
PY

docker compose logs --no-color nginx > "$tmp_dir/nginx.log"
grep -Eiq 'No space left on device|ENOSPC' "$tmp_dir/nginx.log"
