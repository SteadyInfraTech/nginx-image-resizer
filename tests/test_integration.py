import os
import struct
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
ORIGIN_CONTROL_URL = os.environ.get("ORIGIN_CONTROL_URL", "http://127.0.0.1:8081")
SOURCE_ASPECT_RATIO = 4 / 3
URI_STYLE = os.environ.get("URI_STYLE", "prefix")


def selected_uri(path):
    """Translate canonical prefix paths into the configured public URI style."""
    if URI_STYLE not in ("prefix", "suffix"):
        raise RuntimeError("URI_STYLE must be prefix or suffix")
    if URI_STYLE == "suffix":
        import re
        path = re.sub(r"^/(\\d+)x(\\d+)(/[^?]+)", r"\\3/_resize/\\1x\\2", path)
    return path


def set_stale_sample_origin_status(status):
    req = Request(
        ORIGIN_CONTROL_URL + "/__test__/stale-sample-status",
        data=str(status).encode("ascii"),
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    with urlopen(req, timeout=5) as response:
        if response.status != 204:
            raise AssertionError(f"unexpected origin control response: {response.status}")


def request(path, headers=None):
    request_headers = {"User-Agent": "steady-image-resizer-tests/1"}
    if headers:
        request_headers.update(headers)
    req = Request(BASE_URL + selected_uri(path), headers=request_headers)
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def png_dimensions(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("response is not a PNG")
    return struct.unpack(">II", data[16:24])


def webp_dimensions(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AssertionError("response is not WebP")
    position = 12
    while position + 8 <= len(data):
        chunk_type = data[position:position + 4]
        chunk_size = int.from_bytes(data[position + 4:position + 8], "little")
        payload = data[position + 8:position + 8 + chunk_size]
        if len(payload) != chunk_size:
            raise AssertionError("truncated WebP chunk")
        if chunk_type == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(payload[6:8], "little") & 0x3fff
            height = int.from_bytes(payload[8:10], "little") & 0x3fff
            return width, height
        if chunk_type == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2f:
            width = 1 + payload[1] + ((payload[2] & 0x3f) << 8)
            height = 1 + ((payload[2] & 0xc0) >> 6) + (payload[3] << 2) + ((payload[4] & 0x0f) << 10)
            return width, height
        if chunk_type == b"VP8X" and len(payload) >= 10:
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
            return width, height
        position += 8 + chunk_size + (chunk_size & 1)
    raise AssertionError("WebP dimensions not found")


def gif_dimensions(data):
    if data[:6] not in (b"GIF87a", b"GIF89a") or len(data) < 10:
        raise AssertionError("response is not GIF")
    return struct.unpack("<HH", data[6:10])


def jpeg_dimensions(data):
    if data[:2] != b"\xff\xd8":
        raise AssertionError("response is not JPEG")
    position = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            raise AssertionError("invalid JPEG marker")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            break
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            raise AssertionError("invalid JPEG segment")
        if marker in sof_markers:
            if segment_length < 7:
                raise AssertionError("invalid JPEG frame")
            height, width = struct.unpack(">HH", data[position + 3:position + 7])
            return width, height
        position += segment_length
        if marker == 0xDA:
            break
    raise AssertionError("JPEG dimensions not found")


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

    def test_uri_style_configuration_is_supported(self):
        self.assertIn(URI_STYLE, ("prefix", "suffix"))
        status, _, body = request("/77x77/sample.png?uri-style-contract=1")
        self.assertEqual(status, 200)
        assert_fits_resize_box(self, body, 77, 77)

    def test_resize_fits_requested_dimensions_and_returns_png(self):
        status, headers, body = request("/77x77/sample.png")
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers.get("Content-Type", ""))
        assert_fits_resize_box(self, body, 77, 77)

    def test_jpeg_is_resized_and_cached(self):
        path = "/16x16/sample.jpg"
        first_status, first_headers, first_body = request(path)
        second_status, second_headers, second_body = request(path)
        self.assertEqual(200, first_status)
        self.assertEqual(200, second_status)
        self.assertIn("image/jpeg", first_headers.get("Content-Type", ""))
        self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", second_headers.get("X-Cache-Status"))
        width, height = jpeg_dimensions(first_body)
        self.assertLessEqual(width, 16)
        self.assertLessEqual(height, 16)
        self.assertAlmostEqual(width / height, SOURCE_ASPECT_RATIO, delta=0.03)
        self.assertEqual(first_body, second_body)

    def test_gif_is_resized_and_cached(self):
        path = "/77x77/sample.gif"
        first_status, first_headers, first_body = request(path)
        second_status, second_headers, second_body = request(path)
        self.assertEqual(200, first_status)
        self.assertEqual(200, second_status)
        self.assertIn("image/gif", first_headers.get("Content-Type", ""))
        self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", second_headers.get("X-Cache-Status"))
        width, height = gif_dimensions(first_body)
        self.assertLessEqual(width, 77)
        self.assertLessEqual(height, 77)
        self.assertAlmostEqual(width / height, SOURCE_ASPECT_RATIO, delta=0.03)
        self.assertEqual(first_body, second_body)

    @unittest.skipUnless(os.environ.get("VALIDATED_ORIGIN") != "1", "optional validator currently supports PNG, JPEG, and GIF only")
    def test_webp_is_resized_and_cached_when_supported_by_upstream_module(self):
        path = "/77x77/sample.webp"
        first_status, first_headers, first_body = request(path)
        second_status, second_headers, second_body = request(path)
        self.assertEqual(200, first_status)
        self.assertEqual(200, second_status)
        self.assertIn("image/webp", first_headers.get("Content-Type", ""))
        self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", second_headers.get("X-Cache-Status"))
        width, height = webp_dimensions(first_body)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        self.assertLessEqual(width, 77)
        self.assertLessEqual(height, 77)
        self.assertAlmostEqual(width / height, SOURCE_ASPECT_RATIO, delta=0.03)
        self.assertEqual(first_body, second_body)

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

    def test_stale_cached_image_is_served_when_origin_returns_503(self):
        path = "/77x77/stale-sample.png?case=stale-on-503"
        set_stale_sample_origin_status(200)
        try:
            first_status, first_headers, first_body = request(path)
            self.assertEqual(200, first_status)
            self.assertEqual("MISS", first_headers.get("X-Cache-Status"))
            assert_fits_resize_box(self, first_body, 77, 77)

            # The Compose test image overrides the cache TTL to 1s; the
            # default production image keeps the 10m setting from nginx.conf.
            time.sleep(3.0)
            set_stale_sample_origin_status(503)

            stale_status, stale_headers, stale_body = request(path)
            self.assertEqual(200, stale_status)
            self.assertEqual("STALE", stale_headers.get("X-Cache-Status"))
            self.assertEqual(first_body, stale_body)
        finally:
            set_stale_sample_origin_status(200)

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

        # nginx.conf documents all three supported truthy values. Each must
        # bypass both cache lookup and storage, not just the numeric form.
        for value in ("true", "yes"):
            with self.subTest(bypass_cache=value):
                path = f"/77x77/sample.png?version=cache-bypass-{value}&bypass_cache={value}"
                first_status, first_headers, first_body = request(path)
                second_status, second_headers, second_body = request(path)
                self.assertEqual(200, first_status)
                self.assertEqual(200, second_status)
                self.assertEqual("BYPASS", first_headers.get("X-Cache-Status"))
                self.assertEqual("BYPASS", second_headers.get("X-Cache-Status"))
                self.assertEqual(first_body, second_body)

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

    def test_client_host_header_cannot_select_or_poison_origin_content(self):
        # The origin's canonical response for this fixture is version 2.
        expected_status, _, expected_body = request(
            "/77x77/sample.png?version=2"
        )
        self.assertEqual(200, expected_status)

        path = "/77x77/host-sensitive.png?case=fixed-origin-host"
        attacker_status, attacker_headers, attacker_body = request(
            path, headers={"Host": "attacker.example"}
        )
        normal_status, normal_headers, normal_body = request(path)
        self.assertEqual(200, attacker_status)
        self.assertEqual(200, normal_status)
        self.assertEqual("MISS", attacker_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", normal_headers.get("X-Cache-Status"))
        # A client-supplied Host must not select different origin content
        # under a cache key that intentionally does not include that header.
        self.assertEqual(expected_body, attacker_body)
        self.assertEqual(attacker_body, normal_body)
        assert_fits_resize_box(self, attacker_body, 77, 77)

    def test_client_accept_header_cannot_select_or_poison_origin_content(self):
        expected_status, _, expected_body = request("/77x77/sample.png?version=2")
        self.assertEqual(200, expected_status)

        path = "/77x77/accept-sensitive.png?case=fixed-origin-accept"
        client_status, client_headers, client_body = request(
            path, headers={"Accept": "text/html"}
        )
        normal_status, normal_headers, normal_body = request(path)
        self.assertEqual(200, client_status)
        self.assertEqual(200, normal_status)
        self.assertEqual("MISS", client_headers.get("X-Cache-Status"))
        self.assertEqual("HIT", normal_headers.get("X-Cache-Status"))
        # The origin sees a fixed image Accept value regardless of client input.
        self.assertEqual(expected_body, client_body)
        self.assertEqual(client_body, normal_body)
        assert_fits_resize_box(self, client_body, 77, 77)

    def test_client_cookie_and_authorization_cannot_select_cached_origin_content(self):
        expected_status, _, expected_body = request("/77x77/sample.png?version=2")
        self.assertEqual(200, expected_status)

        for header, value in (("Cookie", "variant=attacker"),
                              ("Authorization", "Bearer attacker")):
            with self.subTest(header=header):
                path = f"/77x77/accept-sensitive.png?case={header.lower()}"
                client_status, client_headers, client_body = request(
                    path, headers={header: value}
                )
                normal_status, normal_headers, normal_body = request(path)
                self.assertEqual(200, client_status)
                self.assertEqual(200, normal_status)
                self.assertEqual("MISS", client_headers.get("X-Cache-Status"))
                self.assertEqual("HIT", normal_headers.get("X-Cache-Status"))
                self.assertEqual(expected_body, client_body)
                self.assertEqual(client_body, normal_body)
                assert_fits_resize_box(self, client_body, 77, 77)

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

    @unittest.skipUnless(os.environ.get("VALIDATED_ORIGIN") == "1", "requires the optional validated-origin Compose overlay")
    def test_source_dimensions_are_rejected_before_image_filter_decode(self):
        # The fixture declares 50,000 x 50,000 pixels but contains only a tiny
        # body. The validator must reject it before NGINX image_filter decodes it.
        status, _, body = request("/77x77/dimension-bomb.png")
        self.assertEqual(415, status, body[:200])

    def test_source_larger_than_image_filter_buffer_is_rejected(self):
        status, _, body = request("/77x77/oversized.png")
        self.assertEqual(415, status, body[:200])

    def test_concurrent_requests_for_same_variant(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: request("/137x91/sample.png"), range(8)))
        cache_statuses = [headers.get("X-Cache-Status") for _, headers, _ in results]
        for status, _, body in results:
            self.assertEqual(status, 200)
            assert_fits_resize_box(self, body, 137, 91)

        # proxy_cache_lock should allow one request to populate this key;
        # the concurrent followers should reuse the cached response.
        self.assertEqual(1, cache_statuses.count("MISS"), cache_statuses)
        self.assertEqual(7, cache_statuses.count("HIT"), cache_statuses)

    def test_excess_concurrent_image_requests_are_rejected(self):
        # The configured per-instance limit is 16. Slow, distinct cache keys
        # keep requests in flight long enough to verify overload behavior.
        paths = [f"/77x77/slow.png?request={index}" for index in range(24)]
        with ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(request, paths))

        statuses = [status for status, _, _ in results]
        self.assertGreaterEqual(statuses.count(200), 1, statuses)
        self.assertGreaterEqual(statuses.count(503), 1, statuses)
        self.assertEqual(24, len(statuses))
        self.assertTrue(set(statuses).issubset({200, 503}), statuses)

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
