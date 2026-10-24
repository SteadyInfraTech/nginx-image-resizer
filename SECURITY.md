# Security Policy

This repository is a reference implementation and is not advertised as production-ready.

Do not report exploitable vulnerabilities in public issues. Use GitHub private vulnerability reporting if enabled, or contact the maintainers through the organization profile.

Security assumptions:
- The origin is configured by the operator and is not selected by clients.
- Dimensions are bounded to 1–2048.
- Traversal-like paths are rejected.
- The demo origin serves only fixed fixtures.
- `image_filter_buffer 8M` limits encoded source bytes, not decoded pixel allocation. A small compressed image can declare extremely large dimensions and trigger substantial decoder memory use before resizing; the current NGINX image-filter configuration does not enforce a source-pixel ceiling.
- Treat origin images as trusted input unless a separate decoder validates source dimensions/pixel count before decoding. Do not expose this service to arbitrary untrusted image sources as a security boundary.
- Apply an operating-system/container memory limit and a restart policy, and tune `NGINX_MAX_CONCURRENT_IMAGE_REQUESTS` from measurements. A memory limit contains damage but can still cause the container to be killed; it is not a substitute for decoder-level pixel limits.
- Operators must review access control, request limits, cache storage, image size limits, and upstream trust before adapting this example.
