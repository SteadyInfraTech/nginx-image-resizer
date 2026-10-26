# Steady NGINX Image Resizer

On-demand image resizing with NGINX, using a simple URL format:

```text
/77x77/path/to/image.png
```

NGINX fetches an original image from a fixed, trusted upstream, resizes it, and caches the transformed response. The default request path is one NGINX process; an optional validated-origin mode is available for deployments that need a pre-decode dimension gate. URI style is configurable at Compose runtime (`NGINX_URI_STYLE=prefix|suffix`, default `prefix`) and at Helm install time (`--set uriStyle=prefix|suffix`). The prefix form is `/77x77/path/to/image.png`; the suffix form is `/path/to/image.png/_resize/77x77`. The selected form is the only accepted public route for that deployment. The default setup is designed to run behind a load balancer or reverse proxy that handles public HTTPS.

> **Status:** Reference implementation. CI covers the HTTP request path and cache behavior; deployment-specific performance and security validation are still required.

## Quick start

Requires Docker Engine and the Docker Compose plugin.

Run the integration suite:

```sh
docker compose up --build --abort-on-container-exit --exit-code-from tests
docker compose down --volumes --remove-orphans
```

Run the demo interactively:

```sh
docker compose up --build -d nginx origin
curl -i http://localhost:8080/77x77/sample.png
docker compose down
```

The demo origin serves synthetic PNG fixtures; no external image host is needed. The default Compose stack uses the single-process NGINX path; optional validation is tested separately.

## Runtime hardening

The Compose NGINX service runs with a read-only container root filesystem, drops all Linux capabilities, enables `no-new-privileges`, and mounts bounded writable tmpfs filesystems for the NGINX PID, cache, and temporary files. The cache is ephemeral and limited by the 96 MiB cache tmpfs; the NGINX cache itself is configured for a 64 MiB maximum. The tmpfs is intentionally not persistent across container recreation.

These are defense-in-depth defaults, not a substitute for host-level resource limits, network policy, image updates, or deployment-specific testing. CPU and memory limits are not guessed here; choose them from benchmark measurements.

## Deployment

### Behind a load balancer or reverse proxy

Terminate TLS at the load balancer or reverse proxy and forward HTTP traffic to the container on port `8080`. Publish this port only to a trusted network. The origin and loopback-only transformer should not be exposed publicly.

The demo's host port can be changed with `NGINX_HOST_PORT`. For example, set it to `9080` and use `http://localhost:9080/77x77/sample.png`. This changes only the host-side mapping; the container still listens on `8080`.

To use the suffix URI form with Compose, run `NGINX_URI_STYLE=suffix docker compose up --build`; request `/sample.png/_resize/77x77`. The default prefix form remains `/77x77/sample.png`. Changing this setting selects the route shape at container startup; rebuilds are not required for URI-style changes.

### Direct HTTPS

A separate configuration is provided for deployments where this container terminates TLS itself. Build with `nginx-direct-tls.conf`, publish ports `80` and `443`, and mount a certificate/key pair at runtime:

```sh
# Create the network first if it does not exist, and attach your origin
# container/service to it with the network alias "origin".
docker network create your-private-network

docker build --build-arg NGINX_CONFIG=nginx-direct-tls.conf \\
  --build-arg NGINX_PUBLIC_HOST=images.example.com \\
  -t steady-nginx-image-resizer:direct-tls .
docker run --rm \
  --network your-private-network \
  --read-only \
  --memory "${NGINX_MEMORY_LIMIT:?Set NGINX_MEMORY_LIMIT to a measured container memory budget}" \
  --memory-swap "${NGINX_MEMORY_LIMIT:?Set NGINX_MEMORY_LIMIT to a measured container memory budget}" \
  --cap-drop ALL --cap-add CHOWN --cap-add SETUID --cap-add SETGID --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  --tmpfs /run/nginx:rw,noexec,nosuid,size=1m,mode=0755 \
  --tmpfs /var/lib/nginx/tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --tmpfs /var/cache/nginx:rw,noexec,nosuid,size=96m,mode=1777 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  -p 80:80 -p 443:443 \
  -v "$PWD/tls:/etc/nginx/tls:ro" \
  steady-nginx-image-resizer:direct-tls
```

The mounted directory must contain `tls.crt` and `tls.key`. Build with `NGINX_PUBLIC_HOST` set to the public DNS hostname covered by the certificate (the default is `localhost` for local testing). The HTTP listener redirects to this configured hostname rather than reflecting an untrusted request `Host` header. Ensure the key is readable by the container's NGINX master through normal file ownership and permissions; with the hardened capability set, do not rely on `DAC_OVERRIDE` to read a host-owned key. Keep private keys out of the image and manage renewal through your certificate-management process. Plain HTTP requests redirect to `https://$NGINX_PUBLIC_HOST`; arbitrary client-supplied Host values cannot choose the redirect destination. `/healthz` remains available on port 80 for health checks. The NGINX master binds low ports, while worker processes run as the `nginx` user. Only `CHOWN` (for NGINX cache-directory ownership), `SETUID`/`SETGID` (to start workers as the configured `nginx` user), and `NET_BIND_SERVICE` (for ports 80 and 443) are retained; all other capabilities are dropped. Do not set a container-wide `USER nginx` without separately validating low-port binding, PID creation, and cache/temp directory permissions.

Use an existing Docker network in place of `your-private-network` (or create it as shown above). Attach the origin container/service to that same network with the network alias `origin` and port `8081`; the resizer must join the network as well so `origin:8081` resolves from inside its container. If the origin is managed by Compose, configure the shared network and alias there rather than creating a second origin container. Avoid publishing the origin or loopback transformer.

## Upstream NGINX build

The container is based on the official NGINX Open Source Alpine image, pinned to the `1.30.6` release tag, which packages the matching dynamic image-filter module. The build fails if the expected module file is absent, and CI validates the actual configuration with the module loaded. Keep NGINX and the module version aligned when updating the base image.

## Request contract

- Request format: `/{width}x{height}/{origin-relative-path}`.
- Width and height are bounded to 1–2048.
- At most 16 image requests per instance are processed concurrently by default; excess requests receive HTTP 503. Tune at build time with `--build-arg NGINX_MAX_CONCURRENT_IMAGE_REQUESTS=...` based on measured capacity.
- The upstream origin is fixed by configuration; clients cannot provide an arbitrary origin URL.
- Client request headers are not forwarded to the origin; the resizer sends a fixed `Accept` value so headers such as `Host`, `Accept`, `Cookie`, or `Authorization` cannot select a different origin representation under the same URL-based cache key. Origin authentication via client-forwarded headers is intentionally unsupported.
- Cache keys include the URI and query string, so requested sizes and versioned query variants are cached separately.
- Add `?bypass_cache=1` to skip cache lookup and storage. Values `1`, `true`, and `yes` are recognized. The response includes `X-Cache-Status: BYPASS`.
- Cache bypass does not purge or replace an existing cached entry.
- For source updates, use immutable/versioned paths or a version query such as `?version=2`. A response for an unchanged URL can remain cached until the ten-minute TTL expires.
- `X-Cache-Status` exposes cache state for diagnostics and tests.

## Network and request flow

The default deployment uses one NGINX process: it fetches originals from the fixed trusted origin, applies `image_filter`, and caches resized response bytes. An optional validator service can be placed between NGINX and the origin when a deployment needs a header-based dimension gate; this adds another service and supports PNG/GIF/JPEG only.

```text
Client / load balancer
        |
        v
NGINX :8080 -- cache hit --> return cached image
    |
    | cache miss
    v
Fixed trusted image origin :8081

Optional validated-origin mode:
NGINX image filter --> private validator :8082 --> fixed image origin :8081
```

## Kubernetes + Helm

A minimal Helm chart is available in charts/nginx-image-resizer. It deploys the same NGINX image with a chart-rendered trusted-origin configuration, bounded per-pod cache/temp volumes, non-root/read-only runtime settings, health probes, and a ClusterIP Service. The origin must resolve from the pod before NGINX starts. See [the chart README](charts/nginx-image-resizer/README.md) for installation, resource sizing, cache locality, and image-tag guidance. The chart is tested with Helm lint/render, assertions for hardened runtime settings and health probes, a kind install, resize/cache smoke tests, config-change-triggered rollout, per-replica cache locality, pod replacement while serving requests, scaling, upgrade, and rollback.

## Optional validated-origin mode

The default remains one NGINX process and a fixed trusted origin. To exercise the optional pre-decode dimension gate, use the Compose overlay:

```sh
docker compose -f docker-compose.yml -f docker-compose.validated.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.yml -f docker-compose.validated.yml down --volumes --remove-orphans
```

This mode adds a private Python service that reads bounded origin responses and checks PNG/GIF/JPEG headers before NGINX decodes pixels. It is opt-in because it adds another runtime dependency and does not constitute a complete decoder sandbox.

## CI coverage

The integration suite checks resize dimensions and aspect ratio, cache MISS then HIT, cache bypass without storage, versioned cache keys, invalid dimensions, path traversal attempts, missing origin objects, upstream 503 preservation, corrupt and non-image payloads, oversized originals, concurrent same-key and distinct transformations, overload rejection when concurrent image requests exceed the configured cap, and stale-cache fallback when the origin returns 503 after expiry. CI also exercises direct-TLS resizing and cache behavior under the hardened container runtime flags. The kind workflow deletes one serving pod at two replicas and verifies that ten fresh resize requests still succeed through the Service before the replacement pod becomes ready. It also scales the Deployment to zero, verifies the Service has no endpoints, restores two replicas, and confirms resize traffic recovers. The workflow injects readiness and liveness probe failures: unready pods are excluded from Service endpoints, and liveness failures trigger container restarts while healthy replicas remain available. It also simulates a rolling upgrade with an unpullable image and verifies the default rollout strategy preserves at least two ready Service endpoints and successful image requests until the known-good revision is restored. Deployment-specific rollout-strategy overrides are not covered. Helm smoke also asserts the chart renders its default CPU, memory, and ephemeral-storage requests and limits; it does not simulate OOM kills or claim production resource-pressure coverage.

## Limitations

- The image-filter module is separate and depends on GD; package availability and module paths vary by distribution.
- The official NGINX image-filter module transforms JPEG, GIF, PNG, and WebP when the module and underlying GD build support the format. WebP must be verified against the actual built image. AVIF and HEIC are not promised.
- Transformations consume CPU and memory. `image_filter_buffer 8M` caps encoded source bytes, not decoded pixel allocation. The default trusted-origin mode does not protect against a malicious origin returning a tiny file with extreme dimensions. Keep the origin trusted and constrained, set runtime memory limits, and tune concurrency. Optional validated-origin mode adds a lightweight PNG/GIF/JPEG header parser with defaults of 8 MiB encoded bytes, 8192 per side, and 16,777,216 pixels; it reduces one risk but is not a full decoder sandbox and does not support every format. The direct-TLS example requires `NGINX_MEMORY_LIMIT`.
- Arbitrary sizes can fragment the cache; dimension bounds reduce but do not eliminate this.
- Updating an original at the same path does not automatically invalidate cached variants. Use a versioned URL/query or wait for expiry; there is no purge API.
- CI uses a one-second TTL override for stale-on-503 testing; the default image retains a ten-minute TTL. Origin read-timeout and connection-refused recovery are exercised in CI; a sustained outage over operationally relevant durations remains deployment-specific. High-load behavior under production CPU/memory limits, TLS renewal, and load-balancer integration remain deployment-specific.
- The cache is local to each instance; replicas do not share cache contents automatically. The kind smoke test checks that a unique URL is a MISS then HIT on each of two individual pods, rather than assuming a request through the Service reaches a particular replica.
- This is not a full image CDN or media platform. Advanced codecs, cropping, focal points, authorization, purge APIs, and global delivery are out of scope.

## See also

Official NGINX documentation for the modules used by this project:

- [Image filter module](https://nginx.org/en/docs/http/ngx_http_image_filter_module.html) — image resizing.
- [Proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) — upstream requests, caching, stale responses, and cache locking.
- [Map module](https://nginx.org/en/docs/http/ngx_http_map_module.html) — mapping the cache-bypass query argument.
- [Core HTTP module](https://nginx.org/en/docs/http/ngx_http_core_module.html) — listeners, servers, locations, and routing.
- [Upstream module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html) — fixed-origin configuration.
- [Headers module](https://nginx.org/en/docs/http/ngx_http_headers_module.html) — response headers such as cache status.
- [SSL module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html) — HTTPS listeners and certificate configuration.

## Load benchmarking

A dependency-free load generator reports request throughput, latency percentiles, HTTP status counts, and `X-Cache-Status` counts. It is a measurement tool, not a CI performance gate; results are meaningful only when the host, Docker limits, origin behavior, and cache state are recorded.

Start the demo stack in one terminal:

```sh
docker compose up --build -d nginx origin
```

Run these from the repository root in another terminal:

```sh
# Warm-cache path (the tool warms the URL before measuring)
python3 tools/benchmark.py --mode hit --requests 1000 --concurrency 16

# Cold same-key burst (one miss, then cache hits if cache locking works)
python3 tools/benchmark.py --mode stampede --requests 1000 --concurrency 16

# Cache-bypass path (always exercises transformation/origin work)
python3 tools/benchmark.py --mode bypass --requests 500 --concurrency 16

# Unique cache keys (useful for measuring cold-path pressure)
python3 tools/benchmark.py --mode unique --requests 500 --concurrency 16

docker stats --no-stream
docker compose down
```

The Load Stress workflow runs 500 requests per mode on pull requests and 1,000 on scheduled/manual runs, at concurrency 12 (below the default 16-request cap), and archives the JSON reports. The Cache Storage Failure workflow fills a deliberately tiny writable cache filesystem and verifies that origin responses still succeed when cache writes fail with ENOSPC. It checks status/cache correctness, not a machine-independent latency target. Repeat at several concurrency levels (for example 1, 4, 8, 16, 32) and record the container memory/CPU from `docker stats`. Use a representative source image and realistic request mix. Do not infer a safe production concurrency limit from a single run or from CI timing; choose limits from sustained measurements and an explicit latency/error budget. The benchmark exits non-zero if requests fail or return a non-2xx status.

## Development

```sh
docker compose config
docker compose up --build --abort-on-container-exit --exit-code-from tests
docker compose down --volumes --remove-orphans
```

Do not make performance claims until benchmarks have been run on a stated environment.

## License

BSD 2-Clause. See [LICENSE](LICENSE).

Copyright © 2026 Steady Infrastructure LLC.
