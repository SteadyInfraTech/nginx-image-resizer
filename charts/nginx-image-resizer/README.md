# NGINX Image Resizer Helm chart

This chart deploys the trusted-origin, single-NGINX-process request path. It does not deploy an image origin or the optional validator service.

## Install

The origin must be reachable over HTTP from the pod before NGINX starts. By default the chart expects a Kubernetes Service named origin in the same namespace on port 8081.

    helm upgrade --install image-resizer ./charts/nginx-image-resizer \
      --set origin.host=origin.default.svc.cluster.local \
      --set origin.port=8081 \
      --set image.tag=1.0.0

Use an immutable release tag or, preferably, an image digest for production:

    helm upgrade --install image-resizer ./charts/nginx-image-resizer \
      --set origin.host=origin.default.svc.cluster.local \
      --set image.digest=sha256:<64-hex-character-digest>

The chart creates a ClusterIP Service. Terminate public TLS at an Ingress controller or external load balancer; this chart intentionally does not install either. The image publishing workflow pushes the main tag and semantic-version tags to GHCR. Make the GHCR package public for unauthenticated pulls, or set imagePullSecrets for a private package.

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
