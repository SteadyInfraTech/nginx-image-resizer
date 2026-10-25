# Product charter and v1.0.0 scope

## Product promise

Steady NGINX Image Resizer is a reliable, understandable reference implementation for on-demand image resizing and proxy caching using upstream NGINX and `ngx_http_image_filter_module`. It should be straightforward to run, inspect, test, and adapt—not a general-purpose media platform.

The guiding rule is: keep the request path simple, make the engineering around it reliable, and add runtime components only when a deployment requirement justifies their cost.

## Supported deployment shapes

- **Default:** one NGINX process with a fixed, trusted origin. NGINX validates the request path and dimensions, fetches the source, applies the image filter, and caches the transformed response.
- **Optional validated-origin mode:** a separate private service checks bounded PNG/GIF/JPEG headers before NGINX decodes the source. This is a defense-in-depth option, not a full decoder sandbox and not the default.
- **Docker Compose:** supported for deterministic tests, demos, and small deployments.
- **Kubernetes + Helm:** the intended reusable deployment target for v1.0.0. The initial chart is implemented, and CI passes a kind-based install/upgrade smoke test against the same application image and documented request semantics.
- **Out of scope for v1.0.0:** AWS AMI, globally shared cache, image CDN, external cache/control plane, arbitrary remote-origin URLs, and a custom image-processing engine.

## Trust and security model

The default mode assumes the configured origin is trusted to supply images. The origin is fixed by configuration; clients cannot choose an arbitrary origin host or forward headers that select a different cached representation.

The NGINX image-filter buffer limits encoded bytes, not decoded pixel allocation. Runtime memory limits, bounded concurrency, upstream timeouts, constrained origin access, and a clear failure policy remain required. Deployments accepting less-trusted source images should evaluate optional validation or a proper decoder boundary; the lightweight validator must not be represented as complete protection against malformed images.

## Request and transformation contract

- Request shape: `/{width}x{height}/{origin-relative-path}`.
- Width and height are positive and bounded; invalid dimensions and traversal-like paths are rejected.
- `resize` preserves aspect ratio and fits within the requested box. Crop is a distinct operation and is not part of the current URL contract.
- The deployed upstream module's actual capabilities define format support. NGINX documents JPEG, GIF, PNG, and WebP, with WebP dependent on GD build support. CI must test formats against the actual image before they are advertised.
- AVIF/HEIC support, animated-image preservation, and metadata/color-profile preservation are not promised without explicit tests and a supported implementation.
- Cache keys separate requested dimensions, source paths, and query-string versions. Cache bypass skips lookup and storage; it is not a purge operation.
- Cached transformed bytes are local to each NGINX instance. Replicas do not automatically share cache contents or invalidation state.

## v1.0.0 release gates

1. **Build provenance:** use an official upstream NGINX image/module pairing; pin the release; test that the dynamic module loads; document and exercise an update process.
2. **Request correctness:** dimensions, traversal, errors, content types, resize behavior, and cache status are covered by deterministic integration tests.
3. **Cache correctness:** cache-key isolation, same-key request coalescing, bypass semantics, stale-on-error policy, source versioning, and cache storage failures have explicit tests or documented boundaries.
4. **Load containment:** concurrency and upstream timeouts are bounded; cold-cache bursts, slow origins, overload responses, and recovery are tested. No production capacity claim is made without repeatable measurements.
5. **Runtime security:** least privilege, read-only filesystem, explicit writable paths, resource limits, trusted origin configuration, and dependency/image scanning are covered.
6. **Deployment contract:** Docker Compose remains working; Helm lint/render/install/upgrade and workload smoke tests pass in Kubernetes.
7. **Operations:** health/readiness behavior, logs, cache persistence/locality, configuration, upgrades, rollback, and known limitations are documented.
8. **Scope discipline:** no feature is a release blocker unless required by the product promise or a demonstrated correctness/security gap.

## Known limitations to disclose

- NGINX image-filter is based on GD; format and behavior depend on the exact build.
- The encoded input buffer does not cap decoded pixel allocation.
- Local caches are per instance and may independently transform the same source on separate replicas.
- Source updates at an unchanged URL may remain stale until expiry; use versioned URLs/query strings.
- High-load resilience is not established by CI success alone; release validation must exercise representative concurrent cold misses and failure conditions.
