# NGINX Image Resizer Helm chart

This chart deploys the trusted-origin, single-NGINX-process request path. It does not deploy an image origin or the optional validator service.

**New to the chart?** Follow the [15-minute Kubernetes quickstart](../../docs/kubernetes-quickstart.md) to install into a cluster, verify a resized response and cache HIT, and understand how application traffic must be routed.

## Install

The origin must be reachable over HTTP from the pod before NGINX starts. By default the chart expects a Kubernetes Service named origin in the same namespace on port 8081. URI routing defaults to `uriStyle: prefix` (`/77x77/products/item.png`). Set `--set uriStyle=suffix` to use `/products/item.png/_resize/77x77`; only the selected style is enabled.

    helm upgrade --install image-resizer ./charts/nginx-image-resizer \
      --set origin.host=origin.default.svc.cluster.local \
      --set origin.port=8081 \
      --set image.tag=1.0.0

Use an immutable release tag or, preferably, an image digest for production:

    helm upgrade --install image-resizer ./charts/nginx-image-resizer \
      --set origin.host=origin.default.svc.cluster.local \
      --set image.digest=sha256:<64-hex-character-digest>

The chart creates a ClusterIP Service. Terminate public TLS at an Ingress controller or external load balancer; this chart intentionally does not install either. The Deployment uses a `preStop` hook to ask NGINX to gracefully quit and waits for the master PID file to disappear before kubelet sends its final termination signal, allowing active requests to drain within `terminationGracePeriodSeconds`. The image publishing workflow pushes the main tag and semantic-version tags to GHCR. Make the GHCR package public for unauthenticated pulls, or set imagePullSecrets for a private package.

### Optional egress NetworkPolicy

The chart can optionally restrict resizer pod egress with `--set networkPolicy.enabled=true`. The policy allows TCP to the configured origin port on pods matching `networkPolicy.origin.podLabels` and `networkPolicy.origin.namespaceLabels`, plus UDP/TCP DNS to CoreDNS in `kube-system`. Set those selectors to match the real in-cluster origin. Use `networkPolicy.extraEgress` for explicitly required external destinations or additional services; review each rule carefully. The policy is disabled by default because NetworkPolicy resources are only enforced when the cluster CNI supports them. The dedicated `Network policy enforcement` CI workflow installs Calico in kind and proves that the configured origin remains reachable while an unrelated Service is blocked. This does not validate a customer cluster's other policies, ingress isolation, cloud firewalls, or external-origin CIDRs.

The `1.0.0` tag above is an example: use it only after that image tag has been published. The Helm chart has its own independent SemVer version in `Chart.yaml`; `appVersion` records the application version represented by the chart and should be updated with an application release. A chart version bump is required for chart changes, even when the application image version does not change.

To roll back to the previous Helm revision after an upgrade:

    helm history image-resizer
    helm rollback image-resizer 1 --wait

Replace `1` with the revision you intend to restore. Rollback restores the prior chart values and workload template; it does not restore ephemeral per-pod cache contents.

## Resource and cache behavior

- The default per-pod concurrency cap is 4 to align with the default 512 MiB memory limit. Tune the cap and resources together for the source-image sizes you actually serve.
- Each pod has its own bounded ephemeral cache. Scaling replicas does not create a shared cache; cold misses can be repeated on different pods.
- Cache and temporary storage are bounded with emptyDir.sizeLimit. Cache contents are lost when a pod is replaced.
- image_filter_buffer bounds encoded source bytes, not decoded pixel allocation. The configured origin must be trusted and should enforce source dimension/size limits. Optional validated-origin mode is available in Docker Compose but is not enabled by this chart.
- Supported formats depend on the image-filter module and its GD build. CI tests JPEG, GIF, PNG, and WebP against the built image. Animation and metadata preservation are not promised.

## Values to review before production

At minimum set origin.host, choose an immutable image.tag or image.digest, and size resources, nginx.maxConcurrentImageRequests, cache limits, and temporary storage for your environment. The chart has no HPA, Ingress, PVC, global cache, or automatic origin discovery.
