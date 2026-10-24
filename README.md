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

## Deployment

### Behind a load balancer or reverse proxy

Terminate TLS at the load balancer or reverse proxy and forward HTTP traffic to the container on port `8080`. Publish this port only to a trusted network. The origin and loopback-only transformer should not be exposed publicly.

The demo's host port can be changed with `NGINX_HOST_PORT`. For example, set it to `9080` and use `http://localhost:9080/77x77/sample.png`. This changes only the host-side mapping; the container still listens on `8080`.

### Direct HTTPS

The default configuration does not terminate TLS. For direct HTTPS, use a dedicated NGINX configuration with listeners on ports `80` and `443`, redirect HTTP to HTTPS, and mount certificates and keys at runtime. Do not bake private keys into the image. Keep certificate renewal in your deployment's certificate-management process. The NGINX master binds low ports; worker processes run as the `nginx` user. A container-wide non-root setting needs separate validation for port binding, PID creation, and cache/temp directory permissions.

## Request contract

- Request format: `/{width}x{height}/{origin-relative-path}`.
- Width and height are bounded to 1–2048.
- The upstream origin is fixed by configuration; clients cannot provide an arbitrary origin URL.
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

The integration suite checks resize dimensions and aspect ratio, cache MISS then HIT, cache bypass without storage, versioned cache keys, invalid dimensions, path traversal attempts, missing origin objects, upstream 503 preservation, corrupt and non-image payloads, oversized originals, concurrent same-key and distinct transformations, and stale-cache fallback when the origin returns 503 after expiry.

## Limitations

- The image-filter module is separate and depends on GD; package availability and module paths vary by distribution.
- The demo tests PNG only and makes no claims about WebP, AVIF, animated images, or metadata/profile preservation.
- Transformations consume CPU and memory. The 8 MiB image-filter buffer is not a complete resource budget.
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
