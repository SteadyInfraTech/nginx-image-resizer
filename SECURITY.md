# Security Policy

This repository is a reference implementation and is not advertised as production-ready.

Do not report exploitable vulnerabilities in public issues. Use GitHub private vulnerability reporting if enabled, or contact the maintainers through the organization profile.

Security assumptions:
- The origin is configured by the operator and is not selected by clients.
- Dimensions are bounded to 1–2048.
- Traversal-like paths are rejected.
- The demo origin serves only fixed fixtures.
- A private pre-decode validator now parses PNG/GIF/JPEG headers without decoding pixels and rejects sources exceeding 8 MiB encoded bytes, 8192 pixels on either side, or 16,777,216 total pixels by default. It forwards only validated source bytes to NGINX image_filter.
- The validator is a lightweight format-header gate, not a full image decoder or proof that all malformed files are safe. Keep the origin constrained, update the validator/runtime, and retain operating-system/container memory limits.
- Apply an operating-system/container memory limit and a restart policy, and tune `NGINX_MAX_CONCURRENT_IMAGE_REQUESTS` from measurements. Accepted images still consume decoder memory, and a memory limit can still cause the container to be killed.
- Operators must review access control, request limits, cache storage, image size limits, and upstream trust before adapting this example.
