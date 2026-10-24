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
        with urlopen(req, timeout=5) as response:
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

    def test_path_traversal_is_rejected(self):
        status, _, _ = request("/77x77/../sample.png")
        self.assertEqual(400, status)

    def test_missing_origin_object_returns_not_found(self):
        status, _, _ = request("/77x77/missing.png")
        self.assertEqual(404, status)

    def test_non_image_origin_payload_is_not_served_as_image(self):
        status, _, _ = request("/77x77/not-an-image.png")
        self.assertGreaterEqual(status, 400)

    def test_concurrent_requests_for_same_variant(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: request("/137x91/sample.png"), range(8)))
        for status, _, body in results:
            self.assertEqual(status, 200)
            assert_fits_resize_box(self, body, 137, 91)

if __name__ == "__main__":
    unittest.main()
