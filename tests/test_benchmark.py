import importlib.util
import pathlib
import subprocess
import sys
import unittest


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
