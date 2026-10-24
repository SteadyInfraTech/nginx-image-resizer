# Contributing

1. Make changes on a branch and open a pull request.
2. Explain user-visible behavior and security implications.
3. Run `docker compose config` and `docker compose up --build --abort-on-container-exit --exit-code-from tests`.
4. Add or update black-box integration tests for behavior changes.
5. Do not claim performance improvements without reproducible measurements.
6. Keep dependency versions explicit and document unavoidable floating versions.
