# Steady NGINX Image Resizer

On-demand image resizing with NGINX, using a simple URL format:

```text
/77x77/path/to/image.png
```

NGINX fetches an original image from a fixed upstream, resizes it, and caches the transformed response. The default setup is designed to run behind a load balancer or reverse proxy that handles public HTTPS.

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

The demo origin serves synthetic PNG fixtures; no external image host is needed.

## Runtime hardening

The Compose NGINX service runs with a read-only container root filesystem, drops all Linux capabilities, enables `no-new-privileges`, and mounts bounded writable tmpfs filesystems for the NGINX PID, cache, and temporary files. The cache is ephemeral and limited by the 96 MiB cache tmpfs; the NGINX cache itself is configured for a 64 MiB maximum. The tmpfs is intentionally not persistent across container recreation.

These are defense-in-depth defaults, not a substitute for host-level resource limits, network policy, image updates, or deployment-specific testing. CPU and memory limits are not guessed here; choose them from benchmark measurements.

## Deployment

### Behind a load balancer or reverse proxy

Terminate TLS at the load balancer or reverse proxy and forward HTTP traffic to the container on port `8080`. Publish this port only to a trusted network. The origin and loopback-only transformer should not be exposed publicly.

The demo's host port can be changed with `NGINX_HOST_PORT`. For example, set it to `9080` and use `http://localhost:9080/77x77/sample.png`. This changes only the host-side mapping; the container still listens on `8080`.

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

One NGINX process serves the edge on port `8080` and a transformer on `127.0.0.1:8082`. The edge caches resized response bytes; the transformer is loopback-only.

```text
Client / load balancer
        |
        v
NGINX edge :8080 -- cache hit --> return cached image
        |
        | cache miss
        v
NGINX transformer 127.0.0.1:8082
        |
        v
Fixed image origin :8081
```

## CI coverage

The integration suite checks resize dimensions and aspect ratio, cache MISS then HIT, cache bypass without storage, versioned cache keys, invalid dimensions, path traversal attempts, missing origin objects, upstream 503 preservation, corrupt and non-image payloads, oversized originals, concurrent same-key and distinct transformations, overload rejection when concurrent image requests exceed the configured cap, and stale-cache fallback when the origin returns 503 after expiry. CI also exercises direct-TLS resizing and cache behavior under the hardened container runtime flags.

## Limitations

- The image-filter module is separate and depends on GD; package availability and module paths vary by distribution.
- The demo tests PNG only and makes no claims about WebP, AVIF, animated images, or metadata/profile preservation.
- Transformations consume CPU and memory. The 8 MiB image-filter buffer and 16-request concurrency cap reduce exposure but are not a complete resource budget; benchmark and tune both against deployment-specific CPU and memory limits.
- Arbitrary sizes can fragment the cache; dimension bounds reduce but do not eliminate this.
- Updating an original at the same path does not automatically invalidate cached variants. Use a versioned URL/query or wait for expiry; there is no purge API.
- CI uses a one-second TTL override for stale-on-503 testing; the default image retains a ten-minute TTL. Timeout behavior, sustained origin failure, high-load behavior, TLS renewal, and load-balancer integration need deployment-specific testing.
- The cache is local to each instance; replicas do not share cache contents automatically.
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
# Warm-cache path (repeat the same URL)
python3 tools/benchmark.py --mode hit --requests 1000 --concurrency 16

# Cache-bypass path (always exercises transformation/origin work)
python3 tools/benchmark.py --mode bypass --requests 500 --concurrency 16

# Unique cache keys (useful for measuring cold-path pressure)
python3 tools/benchmark.py --mode unique --requests 500 --concurrency 16

docker stats --no-stream
docker compose down
```

Repeat at several concurrency levels (for example 1, 4, 8, 16, 32) and record the container memory/CPU from `docker stats`. Use a representative source image and realistic request mix. Do not infer a safe production concurrency limit from a single run or from CI timing; choose limits from sustained measurements and an explicit latency/error budget. The benchmark exits non-zero if requests fail or return a non-2xx status.

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
