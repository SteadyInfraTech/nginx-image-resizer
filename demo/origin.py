from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import struct
import threading
import time
import zlib


def png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)


def make_png(width=320, height=240, color=(59, 130, 196)):
    row = b"\x00" + bytes(color) * width
    raw = row * height
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw))
            + png_chunk(b"IEND", b""))


def make_oversized_png():
    # A valid small PNG with a large ancillary chunk makes the encoded source
    # exceed NGINX image_filter_buffer without requiring a huge pixel matrix.
    base = make_png()
    large_metadata = b"x" * (9 * 1024 * 1024)
    return base[:33] + png_chunk(b"tEXt", large_metadata) + base[33:]


PNG = make_png()
PNG_VERSION_2 = make_png(color=(196, 82, 59))
CORRUPT_PNG = b"\x89PNG\r\n\x1a\n" + b"not-a-valid-png-chunk"
OVERSIZED_PNG = make_oversized_png()
STALE_SAMPLE_AVAILABLE = True
STALE_SAMPLE_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/__test__/stale-sample-status":
            self.send_error(405)
        elif parsed.path == "/stale-sample.png":
            with STALE_SAMPLE_LOCK:
                available = STALE_SAMPLE_AVAILABLE
            if not available:
                body = b"origin temporarily unavailable"
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = PNG
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/slow.png":
            # Deterministic slow fixture for exercising the NGINX concurrency cap.
            time.sleep(1.0)
            body = PNG
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/host-sensitive.png":
            # Regression fixture: an untrusted Host must not select origin content.
            body = PNG if self.headers.get("Host") == "attacker.example" else PNG_VERSION_2
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/accept-sensitive.png":
            # A client Accept header must not select a different cached variant.
            body = PNG if self.headers.get("Accept") == "text/html" else PNG_VERSION_2
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/sample.png":
            body = PNG_VERSION_2 if query.get("version") == ["2"] else PNG
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/corrupt.png":
            body = CORRUPT_PNG
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/oversized.png":
            body = OVERSIZED_PNG
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/not-an-image.png":
            body = b"this is not an image"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/origin-unavailable.png":
            body = b"origin temporarily unavailable"
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        global STALE_SAMPLE_AVAILABLE
        parsed = urlsplit(self.path)
        if parsed.path != "/__test__/stale-sample-status":
            self.send_error(404)
            return
        try:
            status = int(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        if status not in (200, 503):
            self.send_error(400)
            return
        with STALE_SAMPLE_LOCK:
            STALE_SAMPLE_AVAILABLE = status == 200
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
