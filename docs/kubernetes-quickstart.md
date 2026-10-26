# Kubernetes quickstart: first resized image in 15 minutes

This walkthrough is the first-customer acceptance path for the Kubernetes + Helm product. It assumes you already have a Kubernetes cluster and a trusted HTTP image origin reachable from that cluster. It uses the current `main` image for evaluation only; do not use a mutable tag as a production pin.

## What you will prove

- Helm installs the resizer into a clean namespace.
- A request is fetched from your configured trusted origin and returned resized.
- The second identical request is served from the resizer's cache.
- You can route traffic to the resizer through your existing ingress or load balancer.

## Prerequisites

- `kubectl` configured for a disposable or non-production cluster.
- Helm 3.
- An HTTP origin service reachable from the cluster, serving a known image at a path such as `/sample.png`.
- The origin must be trusted and constrained: this chart's default mode does not validate decoded pixel dimensions before NGINX's image filter processes the source.

Confirm the origin before installing. Substitute your service name, namespace, port, and path:

```sh
kubectl run origin-check --rm -i --restart=Never \
  --image=curlimages/curl:8.12.1 -- \
  curl -fsS -o /dev/null -w 'origin HTTP %{http_code}, bytes %{size_download}\n' \
  http://origin.default.svc.cluster.local:8081/sample.png
```

If the origin is in another namespace, use its full service DNS name. The command should report HTTP 200 and a non-zero byte count.

## Install

The chart creates a ClusterIP Service and does not create an origin, Ingress, or public load balancer. The example below uses the pre-release `main` image and a sample origin Service in the `default` namespace:

```sh
helm upgrade --install nginx-image-resizer ./charts/nginx-image-resizer \
  --namespace image-resizer --create-namespace \
  --set origin.host=origin.default.svc.cluster.local \
  --set origin.port=8081 \
  --set image.tag=main \
  --wait --timeout 5m

kubectl -n image-resizer get pods,svc
kubectl -n image-resizer rollout status deployment/nginx-image-resizer --timeout=5m
```

If you change the Helm release name or chart naming values, use the Deployment and Service names shown by `kubectl get deployments,services -n image-resizer`.

## Verify resize and cache HIT

Forward the ClusterIP Service to your workstation:

```sh
kubectl -n image-resizer port-forward svc/nginx-image-resizer 8080:8080
```

Keep that command running in one terminal. In another terminal, run:

```sh
RUN_ID=$(date +%s)
URL="http://127.0.0.1:8080/77x77/sample.png?acceptance=${RUN_ID}"

curl -fsS -D /tmp/resizer-first.headers -o /tmp/resizer-first.png "$URL"
curl -fsS -D /tmp/resizer-second.headers -o /tmp/resizer-second.png "$URL"

grep -i '^X-Cache-Status: MISS' /tmp/resizer-first.headers
grep -i '^X-Cache-Status: HIT' /tmp/resizer-second.headers
cmp /tmp/resizer-first.png /tmp/resizer-second.png
file /tmp/resizer-second.png
```

Expected results:

- First request reports `X-Cache-Status: MISS`.
- Second request reports `X-Cache-Status: HIT`.
- `cmp` exits successfully because both responses contain identical bytes.
- `file` reports a PNG whose dimensions fit inside the requested 77×77 box while preserving the source aspect ratio. For a source image of 100×74, for example, the expected output is 77×57.

If the origin returns a different source image, the output dimensions will differ; use a known fixture when checking the exact dimensions.

## Route application traffic

The default request contract is `/{width}x{height}/{origin-relative-path}`. For example, `/77x77/products/item.png` asks the resizer to fetch `/products/item.png` from the configured origin and return a resized image. To select the alternative suffix form, install with `--set uriStyle=suffix` and request `/products/item.png/_resize/77x77`. The chart accepts only the configured style; the default remains `prefix`.

To put it into an application path:

1. Configure an existing Ingress controller, gateway, or load balancer to forward the desired image-resize route to the `nginx-image-resizer` Service on port 8080.
2. Change your image URL template or application integration to use the selected URI style: the default `/77x77/` prefix or the optional `/_resize/77x77` suffix. Existing URLs are not rewritten automatically.
3. Keep the origin and resizer Service private to trusted cluster/network paths. Terminate public TLS at your existing ingress or load balancer.
4. Test source-not-found, origin errors, cache behavior, and representative image sizes before directing production traffic.

This is not a transparent drop-in for arbitrary existing image URLs: the caller must use the documented resize URL shape, and the configured origin is fixed rather than supplied per request. Authentication headers from callers are not forwarded to the origin.

## Before production

Do not promote this evaluation configuration as-is:

- Pin an immutable release tag or image digest after a versioned release is published; `main` can change.
- Set CPU, memory, ephemeral-storage, concurrency, and cache limits from representative load tests.
- Keep the origin trusted and enforce source size/dimension limits. The default mode's encoded-byte buffer does not bound decoded pixel allocation.
- Remember each replica has its own ephemeral cache. Scaling out does not create a shared cache, and replacing a pod discards its cache.
- Test your actual ingress/gateway routing, TLS, origin failure behavior, and rollback in a staging environment.

See [the Helm chart README](../charts/nginx-image-resizer/README.md) and [product scope and release gates](PRODUCT.md) for the full deployment contract and limitations.
