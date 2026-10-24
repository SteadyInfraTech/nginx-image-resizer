# Architecture and design decisions

## Request flow

1. Client requests `/{width}x{height}/{relative-origin-path}`.
2. The edge validates dimensions and rejects traversal-like paths.
3. The edge checks its proxy cache.
4. On a miss, the edge proxies to the transformer.
5. The transformer fetches the original from a fixed origin and applies `ngx_http_image_filter_module`.
6. The edge caches the already-transformed response bytes and returns them.

## Why two NGINX roles?

The cache must sit in front of the transformed response if we want cache hits to return already-resized bytes. The edge/transformer split makes this cache boundary explicit and testable.

## Cache key

The key includes scheme, upstream host, and `$uri`. The URI contains dimensions and source path, so variants do not collide. If behavior later depends on query parameters, negotiated formats, authorization, or headers, update and test the cache key before enabling those features.

## Non-goals

No arbitrary client-provided origin URL, distributed cache, upload API, purge API, authorization model, or performance claim. Those would expand the scope beyond the simple reference pattern.
