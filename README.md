# Steady NGINX Image Resizer

A small reference implementation of on-demand image resizing with NGINX, preserving the simple URI model:

    /77x77/path/to/image.png

The image filter module performs the transformation; the proxy module handles upstream requests and caching. One NGINX process serves the public edge on port 8080 and a loopback-only transformer on 127.0.0.1:8082. The edge caches the already-resized response bytes.

**Reference implementation, not production-ready software.** CI integration tests are a core deliverable.

## Quick start

Requires Docker Engine and the Docker Compose plugin.

    docker compose up --build --abort-on-container-exit --exit-code-from tests

To run the demo interactively:

    docker compose up --build -d nginx origin
    curl -i http://localhost:8080/77x77/sample.png
    docker compose down

The origin serves a deterministic synthetic PNG; no external image host is needed.

## Request contract

- /{width}x{height}/{origin-relative-path}
- Width and height are bounded to 1–2048.
- The upstream origin is fixed by configuration; clients cannot provide an arbitrary origin URL.
- The cache key includes the URI, so requested sizes are separate variants.
- X-Cache-Status exposes cache state for demo and test purposes.

## Network exposure

Only the edge service publishes a host port. The transformer server listens on 127.0.0.1:8082 inside the same container, so it is reachable by the edge but not directly reachable from other containers or the host.

## CI coverage

The integration suite exercises the real HTTP service and checks that output dimensions fit the requested resize box while preserving the source aspect ratio, cache MISS then HIT, variant separation, malformed dimensions, traversal-like paths, missing origin objects, non-image responses, and concurrent requests.

## Limitations and threat model

- ngx_http_image_filter_module is a separate module and depends on GD. Package availability and module paths vary by NGINX distribution/build.
- Format support depends on the module and GD build. The demo tests PNG only; it makes no claims about WebP, AVIF, animated images, or metadata/profile preservation.
- Cold transformations consume CPU and memory. Large originals, many sizes, and high concurrency can be expensive.
- Arbitrary sizes can fragment the cache; dimension bounds reduce but do not eliminate this.
- Replacing an original at the same path can leave a cached variant stale until expiry. Prefer immutable/versioned source paths or implement and test invalidation.
- proxy_cache_lock reduces duplicate fills for the same key, but failure/high-load behavior still needs deployment-specific testing.
- The edge cache is local to one instance; replicas do not share cache contents automatically.
- This is not a full image CDN or media platform. Advanced codecs, cropping, focal points, authorization, purge APIs, and global delivery are out of scope.

## Architecture

    client
      | GET /77x77/sample.png
      v
    NGINX edge :8080 -- proxy_cache (URI includes size)
      | cache miss via loopback
      v
    NGINX transformer 127.0.0.1:8082 -- image_filter
      | fetch original over private Compose network
      v
    fixed origin :8081 -- original image

## Development

    docker compose config
    docker compose up --build --abort-on-container-exit --exit-code-from tests
    docker compose down -v

Do not make performance claims until benchmarks have been run on a stated environment.

## License

BSD 2-Clause. See LICENSE.

Copyright © 2026 Steady Infrastructure LLC.
