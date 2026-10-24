# Security Policy

This repository is a reference implementation and is not advertised as production-ready.

Do not report exploitable vulnerabilities in public issues. Use GitHub private vulnerability reporting if enabled, or contact the maintainers through the organization profile.

Security assumptions:
- The origin is configured by the operator and is not selected by clients.
- Dimensions are bounded to 1–2048.
- Traversal-like paths are rejected.
- The demo origin serves only fixed fixtures.
- Operators must review access control, request limits, cache storage, image size limits, and upstream trust before adapting this example.
