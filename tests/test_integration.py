import os
import struct
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
SOURCE_ASPECT_RATIO = 4 / 3


def request(path):
    req = Request(BASE_URL + path, headers={"User-Agent": "steady-image-resizer-tests/1"})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def png_dimensions(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("response is not a PNG")
    return struct.unpack(">II", data[16:24])


def assert_fits_resize_box(testcase, data, max_width, max_height):
    width, height = png_dimensions(data)
    testcase.assertGreater(width, 0)
    testcase.assertGreater(height, 0)
    testcase.assertLessEqual(width, max_width)
    testcase.assertLessEqual(height, max_height)
    testcase.assertAlmostEqual(width / height, SOURCE_ASPECT_RATIO, delta=0.03)


def wait_for_service():
    for _ in range(40):
        try:
            status, _, _ = request("/healthz")
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("NGINX did not become ready")


class ImageResizerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wait_for_service()

    def test_resize_fits_requested_dimensions_and_returns_png(self):
        status, headers, body = request("/77x77/sample.png")
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers.get("Content-Type", ""))
        assert_fits_resize_box(self, body, 77, 77)

    def test_proxy_cache_miss_then_hit(self):
        path = "/91x63/sample.png"
        first_status, first_headers, first_body = request(path)
        second_status, second_headers, second_body = request(path)
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", second_headers.get("X-Cache-Status"))
        assert_fits_resize_box(self, first_body, 91, 63)
        self.assertEqual(first_body, second_body)

    def test_bypass_cache_argument_skips_lookup_and_storage(self):
        bypass_path = "/77x77/sample.png?version=cache-bypass&bypass_cache=1"
        first_status, first_headers, first_body = request(bypass_path)
        second_status, second_headers, second_body = request(bypass_path)
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual("BYPASS", first_headers.get("X-Cache-Status"))
        self.assertEqual("BYPASS", second_headers.get("X-Cache-Status"))
        self.assertEqual(first_body, second_body)

        normal_path = "/77x77/sample.png?version=cache-bypass"
        normal_first_status, normal_first_headers, _ = request(normal_path)
        normal_second_status, normal_second_headers, _ = request(normal_path)
        self.assertEqual(normal_first_status, 200)
        self.assertEqual(normal_second_status, 200)
        self.assertEqual("MISS", normal_first_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", normal_second_headers.get("X-Cache-Status"))

    def test_cache_busting_query_fetches_changed_source_at_same_path(self):
        first_status, first_headers, first_body = request("/77x77/sample.png?version=1")
        second_status, second_headers, second_body = request("/77x77/sample.png?version=2")
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
        self.assertEqual("MISS", second_headers.get("X-Cache-Status"))
        assert_fits_resize_box(self, first_body, 77, 77)
        assert_fits_resize_box(self, second_body, 77, 77)
        self.assertNotEqual(first_body, second_body)

    def test_different_sizes_are_distinct_variants(self):
        _, _, small = request("/31x29/sample.png")
        _, _, large = request("/111x87/sample.png")
        assert_fits_resize_box(self, small, 31, 29)
        assert_fits_resize_box(self, large, 111, 87)
        self.assertNotEqual(png_dimensions(small), png_dimensions(large))

    def test_invalid_dimensions_are_rejected(self):
        for path in ("/0x10/sample.png", "/01x10/sample.png", "/2049x10/sample.png",
                     "/10x2049/sample.png", "/abc/sample.png"):
            with self.subTest(path=path):
                status, _, _ = request(path)
                self.assertEqual(400, status)

    def test_literal_and_encoded_path_traversal_are_rejected(self):
        paths = (
            "/77x77/../sample.png",
            "/77x77/%2e%2e/sample.png",
            "/77x77/%2e%2e%2fsample.png",
            "/77x77/%252e%252e%252fsample.png",
        )
        for path in paths:
            with self.subTest(path=path):
                status, _, _ = request(path)
                self.assertIn(status, (400, 404), f"unexpected traversal response for {path}")

    def test_missing_origin_object_returns_not_found(self):
        status, _, _ = request("/77x77/missing.png")
        self.assertEqual(404, status)

    def test_origin_503_is_preserved_through_image_filter(self):
        status, _, _ = request("/77x77/origin-unavailable.png")
        self.assertEqual(503, status)

    def test_corrupt_image_returns_unsupported_media_error(self):
        status, _, _ = request("/77x77/corrupt.png")
        self.assertEqual(415, status)

    def test_non_image_origin_payload_is_not_served_as_image(self):
        status, _, _ = request("/77x77/not-an-image.png")
        self.assertGreaterEqual(status, 400)

    def test_source_larger_than_image_filter_buffer_is_rejected(self):
        status, _, body = request("/77x77/oversized.png")
        self.assertEqual(415, status, body[:200])

    def test_concurrent_requests_for_same_variant(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: request("/137x91/sample.png"), range(8)))
        statuses = [status for status, _, _ in results]
        cache_statuses = [headers.get("X-Cache-Status") for _, headers, _ in results]
        for status, _, body in results:
            self.assertEqual(status, 200)
            assert_fits_resize_box(self, body, 137, 91)

        # proxy_cache_lock should allow one request to populate this key;
        # the concurrent followers should reuse the cached response.
        self.assertEqual(1, cache_statuses.count("MISS"), cache_statuses)
        self.assertEqual(7, cache_statuses.count("HIT"), cache_statuses)

    def test_concurrent_distinct_transformations_complete_successfully(self):
        paths = [f"/{width}x{height}/sample.png"
                 for width, height in ((71, 53), (73, 55), (79, 59), (83, 61),
                                       (89, 67), (97, 71), (101, 73), (107, 79))]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(request, paths))
        for path, (status, _, body) in zip(paths, results):
            with self.subTest(path=path):
                self.assertEqual(status, 200)
                width, height = (int(value) for value in path.split("/")[1].split("x"))
                assert_fits_resize_box(self, body, width, height)


if __name__ == "__main__":
    unittest.main()
