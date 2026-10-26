# Production operations and failure-recovery coverage

This matrix distinguishes automated checks from deployment-specific validation. A passing CI workflow is evidence for the exact scenario it exercises, not a blanket production-readiness claim.

## Automated CI coverage

| Scenario | Test or assertion | CI workflow | Coverage notes |
|---|---|---|---|
| Normal resize, format, dimensions, URI contract | `tests/test_integration.py` | `CI` | Prefix and suffix route variants; format support depends on the built image-filter module. |
| Cache MISS/HIT, bypass, versioned variants, header/cache-poisoning defenses | `tests/test_integration.py` | `CI` | Verifies response status, cache headers and bodies. |
| Invalid dimensions, traversal, missing object, corrupt/non-image payload, oversized encoded source | `tests/test_integration.py` | `CI` | Covers request and origin payload failure paths. |
| Origin HTTP 503 and stale response after expiry | `tests/test_integration.py` and `.github/workflows/cache-expiry-refresh.yml` | `CI`, Cache expiry/refresh | Stale fallback is tested with a short TTL override; default TTL is ten minutes. |
| Origin read timeout and service recovery | `tests/test_integration.py` | `CI` | Bounded timeout plus a subsequent successful request; not a sustained-outage test. |
| Origin connection failure / unreachable origin recovery | `.github/workflows/origin-connection-recovery.yml` | Origin outage recovery | A stopped origin must produce HTTP 502 or 504 on a cold key, then the same key must recover as a valid image with a cache MISS. Docker endpoint cleanup can cause either 502 or 504; `tests/test_integration.py` separately asserts 504 for the read-timeout case. |
| Corrupt cache entry recovery | Cache corruption recovery test | Cache corruption recovery | Verifies that a bad cached object can be recovered instead of served as a valid image. |
| Cache filesystem exhaustion (ENOSPC) | Cache storage failure test | Cache storage failure | Verifies requests continue to succeed when cache writes fail; does not establish latency under pressure. |
| Concurrent requests, stampede, overload rejection | Integration suite and benchmark generator | CI, Load stress | Correctness/status checks and archived measurements; no machine-independent latency gate. |
| Graceful SIGTERM with in-flight request | Graceful-shutdown workflow | Graceful shutdown | Uses a deliberately slow origin fixture to exercise draining of an active resize. |
| Hardened direct-TLS mode and certificate/key failure cases | Direct-TLS smoke and TLS failure workflow | CI, TLS certificate failures | Ephemeral test certificates and invalid/missing/unreadable certificate cases; not renewal automation. |
| Non-root, read-only root filesystem, dropped capabilities, no privilege escalation | Rendered chart assertions and hardened container smoke | Helm Kubernetes smoke, CI | Assertions cover rendered settings; runtime smoke covers the exercised container mode. |
| Default Kubernetes resource requests and limits are rendered | Helm smoke asserts the chart renders CPU, memory, and ephemeral-storage requests and limits | Helm Kubernetes smoke | Guards the chart defaults against accidental removal; it does not simulate OOM or establish behavior under production workload/resource pressure. |
| Helm lint/render, install, resize/cache, URI-style change, replica scale-up, pod deletion/replacement, rollback | Helm/kind smoke | Helm Kubernetes smoke | Verifies Service requests while one replica is deleted, then waits for replacement and rolls back. |
| Packaged chart install/upgrade | Packaged chart smoke | Helm packaged chart smoke | Exercises the packaged artifact path, not every external release-registry or cluster combination. |
| Image/chart appVersion agreement and published image smoke | Release validator and published-image workflow | CI, Publish image, Published image smoke | Checks version metadata and smoke-tests the published image path. |
| Cache locality across replicas | Helm/kind smoke contacts each pod directly | Helm Kubernetes smoke | A unique URL must be a MISS then HIT on each of two pods, showing each pod owns an independent cache. This does not assert a particular cache hit ratio through the load-balanced Service. |
| ConfigMap change triggers a rollout | Helm/kind smoke compares the pod-template config checksum before and after a URI-style ConfigMap change, then waits for rollout | Helm Kubernetes smoke | Confirms a changed rendered NGINX config changes the pod template and completes a rollout. |
| Kubernetes readiness/liveness failure injection | Helm/kind smoke temporarily points probes at a missing health path, checks readiness withdrawal and liveness-triggered container restart, then restores the probes | Helm Kubernetes smoke | Confirms the failed-readiness pod is excluded from endpoints and liveness restarts a bad pod while existing ready replicas remain available. |
| Failed rolling-upgrade revision preserves Service capacity | Helm/kind smoke changes the Deployment to an unpullable image, asserts at least two ready Service endpoints and a successful in-cluster resize, then restores the known-good Helm revision | Helm Kubernetes smoke | Exercises the default `maxUnavailable: 0`, `maxSurge: 1` strategy under a stalled/broken new revision; deployment-specific strategy overrides are not covered. |
| Zero-ready-endpoint outage and recovery | Helm/kind smoke scales the Deployment to zero, verifies the Service endpoint list is empty, scales back to two replicas, and checks a valid resize response | Helm Kubernetes smoke | Exercises explicit endpoint withdrawal and recovery, but is not a rolling-upgrade simulation. |

## Deployment-specific validation

| Scenario | Why CI does not fully establish it | Required deployment check |
|---|---|---|
| CPU and memory limits, OOM kill/restart, overload under constrained resources | CI runners and container limits do not represent the target node and workload; current load workflow measures but does not define a universal latency threshold. | Benchmark with representative source images and concurrency under the intended limits; verify restart and recovery behavior under an intentionally constrained environment. |
| Sustained origin outage and recovery over operationally relevant durations | Current tests cover timeout/recovery and HTTP 503/stale fallback, not a prolonged outage with realistic traffic. | Run a controlled outage drill and verify error budget, stale behavior, and recovery after the origin returns. |
| TLS certificate renewal and load-balancer integration | Renewal depends on the external certificate manager and deployment topology. | Validate renewal/reload and end-to-end health through the actual load balancer. |
| Production-scale throughput, latency and cache working-set behavior | Shared CI runners cannot provide stable performance baselines. | Run repeatable benchmarks on a recorded host, with resource limits and a representative request mix. |
| Network policy and origin/transformer isolation | Chart smoke tests do not prove the surrounding cluster's policies. | Confirm the origin is private, only the intended Service is exposed, and NetworkPolicy/firewall rules match the deployment. |
| Rolling upgrade with a broken new revision or deployment-specific strategy overrides | CI now injects a non-pullable image during a rolling update and verifies at least two old Service endpoints plus a successful image request remain available, then restores the healthy revision. The chart uses `maxUnavailable: 0` and `maxSurge: 1`. | Validate any deployment-specific override of the rollout strategy in a controlled cluster; retain the default strategy and its availability guarantees. |

## Follow-up priorities

1. Revisit resource-limit/OOM automation only when the test harness can make the outcome deterministic; keep performance thresholds measurement-based.

Update this matrix whenever a test or workflow changes. Keep README statements aligned with the actual checks and retain deployment-specific caveats for conditions CI cannot realistically reproduce.
