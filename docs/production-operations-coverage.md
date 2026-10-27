# Production operations and failure-recovery coverage

Last reconciled: 2026-10-27. This matrix distinguishes automated checks from deployment-specific validation. A passing CI workflow is evidence for the exact scenario it exercises, not a blanket production-readiness claim.

## Automated CI coverage

| Scenario | Test or assertion | CI workflow | Coverage notes |
|---|---|---|---|
| Normal resize, format, dimensions, URI contract | `tests/test_integration.py` | `CI` | Prefix and suffix route variants; format support depends on the built image-filter module. |
| Cache MISS/HIT, bypass, versioned variants, header/cache-poisoning defenses | `tests/test_integration.py` | `CI` | Verifies response status, cache headers and bodies. |
| Invalid dimensions, traversal, missing object, corrupt/non-image payload, oversized encoded source | `tests/test_integration.py` | `CI` | Covers request and origin payload failure paths. |
| Origin HTTP 503 and stale response after expiry | `tests/test_integration.py` and `.github/workflows/cache-expiry-refresh.yml` | `CI`, Cache expiry/refresh | Stale fallback is tested with a short TTL override; default TTL is ten minutes. |
| Origin read timeout and service recovery | `tests/test_integration.py` | `CI` | Bounded timeout plus a subsequent successful request; not a sustained-outage test. |
| Origin connection failure / unreachable origin recovery | `.github/workflows/origin-connection-recovery.yml` | Origin outage recovery | A stopped origin must produce HTTP 502 or 504 on a cold key, then the same key must recover as a valid image with a cache MISS. Docker endpoint cleanup can cause either 502 or 504; integration tests separately assert 504 for the read-timeout case. |
| Corrupt cache entry recovery | Cache corruption recovery test | Cache corruption recovery | Verifies that a bad cached object can be recovered instead of served as a valid image. |
| Cache filesystem exhaustion (ENOSPC) | Cache storage failure test | Cache storage failure | Verifies requests continue to succeed when cache writes fail; does not establish latency under pressure. |
| Concurrent requests, stampede, overload rejection | Integration suite and benchmark generator | CI, Load stress | Correctness/status checks and archived measurements; no machine-independent latency gate. |
| Graceful SIGTERM with in-flight request | Graceful-shutdown workflow | Graceful shutdown | Uses a deliberately slow origin fixture to exercise draining of an active resize. |
| Hardened direct-TLS mode and certificate/key failure cases | Direct-TLS smoke and TLS failure workflow | CI, TLS certificate failures | Ephemeral test certificates and invalid/missing/unreadable certificate cases; not renewal automation. |
| Non-root, read-only root filesystem, dropped capabilities, no privilege escalation | Rendered chart assertions and hardened container smoke | Helm Kubernetes smoke, CI | Assertions cover rendered settings; runtime smoke covers the exercised container mode. |
| Default Kubernetes resource requests and limits are rendered | Helm smoke asserts the chart renders CPU, memory, and ephemeral-storage requests and limits | Helm Kubernetes smoke | Guards chart defaults against accidental removal; it does not establish production sizing. |
| Resource-limited resize | Resource-limited resize smoke | Resource-limited resize smoke | Verifies a bounded cold-resize workload at configured CPU/memory limits without unexpected restart; not a production capacity test. |
| OOMKilled restart and recovery | `.github/workflows/kubernetes-oom-recovery.yml` | Kubernetes OOM restart recovery | Deliberately injects a memory-growing process, asserts an `OOMKilled` termination and restart, restores the Helm-managed workload, then verifies a valid resized image. This is fault injection, not evidence that normal requests OOM at defaults. |
| Helm lint/render, install, resize/cache, URI-style change, replica scale-up, pod deletion/replacement, rollback | Helm/kind smoke | Helm Kubernetes smoke | Verifies Service requests while one replica is deleted, waits for replacement and rolls back. |
| Readiness/liveness failure injection and stalled/broken rolling upgrade | Helm/kind smoke | Helm Kubernetes smoke | Verifies readiness withdrawal, liveness restart, old ready capacity and successful requests while an unpullable new image stalls the rollout. Uses chart-default rolling strategy. |
| Zero-ready-endpoint outage and recovery | Helm/kind smoke scales Deployment to zero, verifies empty endpoints, scales back up and retries the real in-cluster Service request for a bounded period | Helm Kubernetes smoke | Retains PNG signature/dimension checks; persistent routing failure still fails the job. Bounded retry accounts for data-plane convergence after endpoints return. |
| ConfigMap change triggers a rollout | Helm/kind smoke compares the pod-template config checksum before/after a URI-style change, waits for rollout and verifies the new route | Helm Kubernetes smoke | Confirms the changed NGINX config changes the pod template and completes a rollout. |
| Cache locality across replicas | Helm/kind smoke contacts each pod directly | Helm Kubernetes smoke | A unique URL must be a MISS then HIT on each of two pods, showing each pod owns an independent cache. Does not assert a particular hit ratio through Service load balancing. |
| Packaged chart install/upgrade | Packaged chart smoke | Helm packaged chart smoke | Exercises the packaged artifact path, not every external release-registry or cluster combination. |
| Published-image tag selection and smoke | Release validator and published-image workflow | CI, Published image Helm smoke | Pull-request/manual runs exercise the mutable `main` image; after a successful versioned publish, the workflow selects and tests the corresponding semantic-version tag. The smoke uses a tag rather than pinning the image digest, so it does not prove artifact immutability. Neither path replaces a customer-environment installation rehearsal. |

## Deployment-specific validation

| Scenario | Why CI does not fully establish it | Required deployment check |
|---|---|---|
| Network-policy isolation | Chart smoke tests do not prove surrounding cluster policies or cloud firewall behavior. | Verify the resizer can reach only the intended origin and required cluster services; prove unrelated namespaces/clients cannot reach internal origin or transformer endpoints. |
| TLS certificate renewal and load-balancer integration | Renewal depends on the external certificate manager and deployment topology. | Validate renewal/rotation, reload and propagation through the actual ingress/load balancer, including expiry alerts and client-visible failure behavior. |
| Sustained origin outage and recovery | Current tests cover bounded timeout/recovery and HTTP 503/stale fallback, not a prolonged outage with realistic traffic. | Run a controlled outage drill covering slow/hung origin, DNS failure, extended outage, alerting, stale behavior and recovery after origin returns. |
| Production-scale throughput, latency and cache working set | Shared CI runners cannot provide stable performance baselines. | Benchmark representative source images and traffic on target-like nodes; record concurrency, p95/p99 latency, error rate, CPU, memory, ephemeral storage and cache behavior, then set budgets from results. |
| Platform-specific rollout and node failures | kind does not reproduce all CNI, service-mesh, node drain, autoscaler or cloud load-balancer behavior. | Rehearse node drain/rescheduling, autoscaling and routing convergence in the actual deployment topology. |
| Customer-environment release acceptance | CI does not validate the target cluster's policy, secrets, registry access or external dependencies. | Install an immutable image digest and chart artifact in a clean target-like cluster, verify origin access and secret handling, then execute upgrade and rollback using actual release artifacts. |

## Readiness interpretation

- CI covers the deterministic scenarios above; it does not establish production readiness or production capacity on its own.
- Record deployment-specific checks with environment, configuration, observed results and date before making corresponding production claims.
- Keep [issue #32](https://github.com/SteadyInfraTech/nginx-image-resizer/issues/32) open until this matrix is reviewed against current workflows and remaining deployment-specific checks are executed or explicitly accepted as release limitations.
- Update this matrix when test behavior or workflow coverage changes.
