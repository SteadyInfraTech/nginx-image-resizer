import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest
import urllib.parse
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "tools" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", BENCHMARK_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class BenchmarkUnitTests(unittest.TestCase):
    def test_nearest_rank_percentiles_use_upper_tail_correctly(self):
        values = list(range(1, 41))
        self.assertEqual(20, benchmark.percentile(values, 0.50))
        self.assertEqual(38, benchmark.percentile(values, 0.95))
        self.assertEqual(40, benchmark.percentile(values, 0.99))
        self.assertEqual(0.0, benchmark.percentile([], 0.99))

    def test_percentile_is_independent_of_input_order(self):
        self.assertEqual(
            benchmark.percentile([1, 2, 3, 4, 5], 0.80),
            benchmark.percentile([5, 3, 1, 4, 2], 0.80),
        )

    def test_query_parameter_is_added_before_fragment(self):
        self.assertEqual(
            "http://example.test/image.png?bypass_cache=1#preview",
            benchmark.add_query_parameter(
                "http://example.test/image.png#preview", "bypass_cache", "1", replace=True
            ),
        )

    def test_bypass_parameter_replaces_existing_duplicates(self):
        self.assertEqual(
            "http://example.test/image.png?keep=yes&bypass_cache=1",
            benchmark.add_query_parameter(
                "http://example.test/image.png?keep=yes&bypass_cache=0&bypass_cache=0",
                "bypass_cache",
                "1",
                replace=True,
            ),
        )

    def _run_mock_benchmark(self, mode, requests=8, concurrency=4):
        urls = []
        output = StringIO()

        def fake_request(url, timeout):
            urls.append(url)
            return benchmark.Result(200, 1.0, "HIT")

        argv = [
            str(BENCHMARK_PATH), "--requests", str(requests),
            "--concurrency", str(concurrency), "--mode", mode,
        ]
        with patch.object(sys, "argv", argv), patch.object(
            benchmark, "request_one", side_effect=fake_request
        ), patch.object(benchmark.time, "time_ns", return_value=123), redirect_stdout(output):
            result = benchmark.main()
        return result, urls, json.loads(output.getvalue())

    def test_hit_mode_warms_cache_before_timed_requests(self):
        result, urls, report = self._run_mock_benchmark("hit")
        self.assertEqual(0, result)
        self.assertEqual(9, len(urls))  # one warm-up plus eight measured requests
        self.assertEqual(1, len(set(urls)))
        self.assertEqual(8, report["requests_completed"])

    def test_stampede_mode_uses_one_unique_cold_key_for_all_requests(self):
        result, urls, report = self._run_mock_benchmark("stampede")
        self.assertEqual(0, result)
        self.assertEqual(8, len(urls))  # no warm-up; the first request should miss
        self.assertEqual(1, len(set(urls)))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)
        self.assertEqual(["123"], query["benchmark_stampede"])
        self.assertEqual("stampede", report["mode"])
        self.assertEqual(8, report["requests_completed"])

    def test_non_finite_timeout_is_rejected_before_requests_start(self):
        for timeout in ("nan", "inf", "-inf"):
            with self.subTest(timeout=timeout):
                result = subprocess.run(
                    [sys.executable, str(BENCHMARK_PATH), f"--timeout={timeout}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn("--timeout must be finite", result.stderr)

    def test_base_url_must_be_absolute_http_or_https(self):
        for base_url in ("localhost:8080", "ftp://example.test", "http://example.test/path?x=1"):
            with self.subTest(base_url=base_url):
                result = subprocess.run(
                    [sys.executable, str(BENCHMARK_PATH), "--base-url", base_url],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn("--base-url", result.stderr)


if __name__ == "__main__":
    unittest.main()
