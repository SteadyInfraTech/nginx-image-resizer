# Production operations and failure-recovery coverage

This matrix distinguishes automated checks from deployment-specific validation. A passing CI workflow is evidence for the exact scenario it exercises, not a blanket production-readiness claim.

## Automated CI coverage

| Scenario | Test or assertion | CI workflow | Coverage notes |
|---|---|---|---|
| Normal resize, format, dimensions, URI contract | `tests/test_integration.py` | `CI` | Prefix and suffix route variants; format support depends on the built image-filter module. |
| Cache MISS/HIT, bypass, versioned variants, header/cache-poisoning defenses | `tests/test_integration.py` | `CI` | Verifies response status, cache headers and bodies. |
| Invalid dimensions, traversal, missing object, corrupt/non-image payload, oversized encoded source | `tests/test_integration.py` | `CI` | Covers request and origin payload failure paths. |
| Origin HTTP 503 and stale response after expiry | `tests/test_integration.py`, `tests/cache-expiry-refresh.yml` workflow | `CI`, Cache expiry/refresh | Stale fallback is tested with a short TTL override; default TTL is ten minutes. |
| Origin read timeout and service recovery | `tests/test_integration.py` | `CI` | Bounded timeout plus a subsequent successful request; not a sustained-outage test. |
| Origin connection refused / unreachable origin recovery | No dedicated deterministic test yet | Not covered | Add an automated test before treating this failure mode as covered. |
| Corrupt cache entry recovery | Cache corruption recovery test | Cache corruption recovery | Verifies that a bad cached object can be recovered instead of served as a valid image. |
| Cache filesystem exhaustion (ENOSPC) | Cache storage failure test | Cache storage failure | Verifies requests continue to succeed when cache writes fail; does not establish latency under pressure. |
| Concurrent requests, stampede, overload rejection | Integration suite and benchmark generator | CI, Load stress | Correctness/status checks and archived measurements; no machine-independent latency gate. |
| Graceful SIGTERM with in-flight request | Graceful-shutdown workflow | Graceful shutdown | Uses a deliberately slow origin fixture to exercise draining of an active resize. |
| Hardened direct-TLS mode and certificate/key failure cases | Direct-TLS smoke and TLS failure workflow | CI, TLS certificate failures | Ephemeral test certificates and invalid/missing/unreadable certificate cases; not renewal automation. |
| Non-root, read-only root filesystem, dropped capabilities, no privilege escalation | Rendered chart assertions and hardened container smoke | Helm Kubernetes smoke, CI | Assertions cover rendered settings; runtime smoke covers the exercised container mode. |
| Helm lint/render, install, resize/cache, URI-style change, replica scale-up, pod deletion/replacement, rollback | Helm/kind smoke | Helm Kubernetes smoke | Verifies Service requests while one replica is deleted, then waits for replacement and rolls back. |
| Packaged chart install/upgrade | Packaged chart smoke | Helm packaged chart smoke | Exercises the packaged artifact path, not every external release-registry or cluster combination. |
| Image/chart appVersion agreement and published image smoke | Release validator and published-image workflow | CI, Publish image, Published image smoke | Checks version metadata and smoke-tests the published image path. |
| Cache locality across replicas | No dedicated assertion for replica-specific cache contents yet | Partial only | Multiple replicas are exercised, but cache isolation/locality is not explicitly asserted. |
| ConfigMap change triggers a rollout | Chart has a config checksum annotation; no explicit rollout assertion yet | Partial only | Template design supports it; behavior should be asserted in kind CI. |

## Deployment-specific validation

| Scenario | Why CI does not fully establish it | Required deployment check |
|---|---|---|
| CPU and memory limits, OOM kill/restart, overload under constrained resources | CI runners and container limits do not represent the target node and workload; current load workflow measures but does not define a universal latency threshold. | Benchmark with representative source images and concurrency under the intended limits; verify restart and recovery behavior under an intentionally constrained environment. |
| Sustained origin outage and recovery over operationally relevant durations | Current tests cover timeout/recovery and HTTP 503/stale fallback, not a prolonged outage with realistic traffic. | Run a controlled outage drill and verify error budget, stale behavior, and recovery after the origin returns. |
| TLS certificate renewal and load-balancer integration | Renewal depends on the external certificate manager and deployment topology. | Validate renewal/reload and end-to-end health through the actual load balancer. |
| Production-scale throughput, latency and cache working-set behavior | Shared CI runners cannot provide stable performance baselines. | Run repeatable benchmarks on a recorded host, with resource limits and a representative request mix. |
| Network policy and origin/transformer isolation | Chart smoke tests do not prove the surrounding cluster's policies. | Confirm the origin is private, only the intended Service is exposed, and NetworkPolicy/firewall rules match the deployment. |
| Kubernetes readiness/liveness failure behavior and rolling upgrade when no endpoints are ready | Current kind workflow verifies probes are rendered, pod replacement with a surviving replica, upgrade and rollback; it does not inject probe failures or deliberately remove all ready endpoints during rollout. | Add deterministic kind tests for failed probes and no-ready-endpoint upgrade behavior before relying on those scenarios. |

## Follow-up priorities

1. Add deterministic CI coverage for origin connection refusal and recovery.
2. Assert that a ConfigMap change causes a new ReplicaSet/rollout.
3. Exercise readiness/liveness failure and rolling upgrade with no ready endpoints in kind.
4. Add a replica-locality assertion or keep locality as an explicitly documented operational property.
5. Revisit resource-limit/OOM automation only when the test harness can make the outcome deterministic; keep performance thresholds measurement-based.

Update this matrix whenever a test or workflow changes. Keep README statements aligned with the actual checks and retain deployment-specific caveats for conditions CI cannot realistically reproduce.
