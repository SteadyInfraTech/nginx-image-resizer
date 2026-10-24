#!/usr/bin/env python3
"""Small, dependency-free HTTP load benchmark for the image resizer."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass


@dataclass
class Result:
    status: int
    elapsed_ms: float
    cache_status: str
    error: str | None = None


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile, rounded to two decimal places."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 2)


def request_one(url: str, timeout: float) -> Result:
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "steady-image-resizer-benchmark/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read()
            status = response.status
            cache_status = response.headers.get("X-Cache-Status", "unreported")
            error = None
    except urllib.error.HTTPError as exc:
        status = exc.code
        cache_status = exc.headers.get("X-Cache-Status", "unreported")
        error = f"HTTP {exc.code}"
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        status = 0
        cache_status = "unreported"
        error = str(exc)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return Result(status, elapsed_ms, cache_status, error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="resizer base URL")
    parser.add_argument("--path", default="/77x77/sample.png", help="image path to request")
    parser.add_argument("--requests", type=int, default=500, help="total requests to issue")
    parser.add_argument("--concurrency", type=int, default=16, help="number of concurrent workers")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-request timeout in seconds")
    parser.add_argument(
        "--mode",
        choices=("hit", "bypass", "unique"),
        default="hit",
        help="hit reuses one URL; bypass skips cache; unique varies the query string",
    )
    args = parser.parse_args()

    if (
        args.requests < 1
        or args.concurrency < 1
        or not math.isfinite(args.timeout)
        or args.timeout <= 0
    ):
        parser.error("--requests and --concurrency must be positive; --timeout must be finite and greater than zero")

    parsed_base = urllib.parse.urlsplit(args.base_url)
    if parsed_base.scheme not in ("http", "https") or not parsed_base.netloc:
        parser.error("--base-url must be an absolute http:// or https:// URL")
    if parsed_base.query or parsed_base.fragment:
        parser.error("--base-url must not include a query string or fragment")

    base = args.base_url.rstrip("/")
    path = "/" + args.path.lstrip("/")
    started = time.perf_counter()

    def worker(worker_id: int) -> list[Result]:
        results: list[Result] = []
        for request_id in range(worker_id, args.requests, args.concurrency):
            url = base + path
            if args.mode == "bypass":
                separator = "&" if "?" in url else "?"
                url += separator + "bypass_cache=1"
            elif args.mode == "unique":
                parsed = urllib.parse.urlsplit(url)
                query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                query.append(("benchmark_request", str(request_id)))
                url = urllib.parse.urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
                )
            results.append(request_one(url, args.timeout))
        return results

    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(worker, worker_id) for worker_id in range(min(args.concurrency, args.requests))]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    elapsed_s = time.perf_counter() - started
    latencies = [result.elapsed_ms for result in results]
    status_counts = Counter(str(result.status) for result in results)
    cache_counts = Counter(result.cache_status for result in results)
    errors = [result.error for result in results if result.error]
    report = {
        "target": base + path,
        "mode": args.mode,
        "requests_requested": args.requests,
        "requests_completed": len(results),
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed_s, 3),
        "requests_per_second": round(len(results) / elapsed_s, 2) if elapsed_s else 0,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0,
            "mean": round(statistics.fmean(latencies), 2) if latencies else 0,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 2) if latencies else 0,
        },
        "http_status_counts": dict(sorted(status_counts.items())),
        "cache_status_counts": dict(sorted(cache_counts.items())),
        "errors": errors[:10],
        "note": "Run on a controlled host; results depend on CPU, memory, Docker limits, origin latency, and cache state.",
    }
    print(json.dumps(report, indent=2))
    return 1 if errors or any(result.status < 200 or result.status >= 300 for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
