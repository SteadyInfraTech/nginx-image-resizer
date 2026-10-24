"""Bounded, pre-decode dimension gate for the NGINX image filter.

This service fetches only from the configured fixed origin. It reads at most
MAX_SOURCE_BYTES + 1 bytes, parses dimensions from PNG/GIF/JPEG headers without
decoding pixels, and forwards image bytes only when dimensions are within the
configured limits. NGINX remains responsible for resizing and caching.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import os
import struct
from urllib.parse import urlsplit

ORIGIN_URL = os.environ.get("ORIGIN_URL", "http://origin:8081").rstrip("/")
MAX_SOURCE_BYTES = int(os.environ.get("MAX_SOURCE_BYTES", str(8 * 1024 * 1024)))
MAX_SOURCE_PIXELS = int(os.environ.get("MAX_SOURCE_PIXELS", str(16_777_216)))
MAX_SOURCE_DIMENSION = int(os.environ.get("MAX_SOURCE_DIMENSION", "8192"))
READ_TIMEOUT_SECONDS = float(os.environ.get("READ_TIMEOUT_SECONDS", "5"))
IMAGE_ACCEPT = "image/png, image/jpeg, image/gif"


class InvalidImage(ValueError):
    pass


def dimensions(data: bytes) -> tuple[int, int, str]:
    """Read dimensions from format headers only; never decode pixel data."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise InvalidImage("invalid PNG header")
        width, height = struct.unpack(">II", data[16:24])
        return width, height, "image/png"

    if data.startswith((b"GIF87a", b"GIF89a")):
        if len(data) < 10:
            raise InvalidImage("invalid GIF header")
        width, height = struct.unpack("<HH", data[6:10])
        return width, height, "image/gif"

    if data.startswith(b"\xff\xd8"):
        pos = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while pos < len(data):
            if data[pos] != 0xFF:
                raise InvalidImage("invalid JPEG marker")
            while pos < len(data) and data[pos] == 0xFF:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                if marker == 0xD9:
                    break
                continue
            if pos + 2 > len(data):
                break
            segment_length = struct.unpack(">H", data[pos:pos + 2])[0]
            if segment_length < 2 or pos + segment_length > len(data):
                raise InvalidImage("invalid JPEG segment length")
            if marker in sof_markers:
                if segment_length < 7:
                    raise InvalidImage("invalid JPEG frame header")
                height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
                return width, height, "image/jpeg"
            pos += segment_length
            if marker == 0xDA:  # Start of scan: no frame header was found.
                break
        raise InvalidImage("JPEG frame dimensions not found")

    raise InvalidImage("unsupported image format")


def validate_image(data: bytes) -> tuple[int, int, str]:
    width, height, content_type = dimensions(data)
    if width < 1 or height < 1:
        raise InvalidImage("image dimensions must be positive")
    if width > MAX_SOURCE_DIMENSION or height > MAX_SOURCE_DIMENSION:
        raise InvalidImage("image dimension limit exceeded")
    if width * height > MAX_SOURCE_PIXELS:
        raise InvalidImage("image pixel limit exceeded")
    return width, height, content_type


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_body(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        self.handle_image_request()

    def do_HEAD(self):
        self.handle_image_request()

    def handle_image_request(self):
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/") or parsed.path.startswith("//"):
            self.send_body(400, b"invalid image path")
            return
        target = ORIGIN_URL + self.path
        req = Request(target, headers={"Accept": IMAGE_ACCEPT, "Host": "origin"})
        try:
            with urlopen(req, timeout=READ_TIMEOUT_SECONDS) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                declared_length = response.headers.get("Content-Length")
                if declared_length:
                    try:
                        if int(declared_length) > MAX_SOURCE_BYTES:
                            self.send_body(415, b"source image exceeds encoded byte limit")
                            return
                    except ValueError:
                        self.send_body(502, b"invalid origin content length")
                        return
                body = response.read(MAX_SOURCE_BYTES + 1)
        except HTTPError as exc:
            # Preserve upstream failure semantics without forwarding arbitrary
            # upstream headers or bodies into the image-filter module.
            self.send_body(exc.code, b"origin request failed")
            return
        except (URLError, TimeoutError, OSError):
            self.send_body(503, b"origin unavailable")
            return

        if status != 200:
            self.send_body(status, b"origin request failed")
            return
        if len(body) > MAX_SOURCE_BYTES:
            self.send_body(415, b"source image exceeds encoded byte limit")
            return
        try:
            width, height, detected_type = validate_image(body)
        except InvalidImage as exc:
            self.send_body(415, str(exc).encode("ascii", "replace"))
            return
        # Do not trust the origin MIME type: the bytes and parsed format decide.
        self.send_body(200, body, detected_type)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    if MAX_SOURCE_BYTES < 24 or MAX_SOURCE_PIXELS < 1 or MAX_SOURCE_DIMENSION < 1:
        raise SystemExit("validator limits must be positive and MAX_SOURCE_BYTES >= 24")
    ThreadingHTTPServer(("0.0.0.0", 8082), Handler).serve_forever()
