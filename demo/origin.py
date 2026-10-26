from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
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
JPEG = base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDADUlKC8oITUvKy88OTU/UIVXUElJUKN1e2GFwarLyL6qurfV8P//1eL/5re6////////////zv//////////////2wBDATk8PFBGUJ1XV53/3Lrc////////////////////////////////////////////////////////////////////wAARCAAYACADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAT/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCYChOAAAAAA//Z")
GIF = base64.b64decode("R0lGODdhQAHwAIEAABh4yAAAAAAAAAAAACwAAAAAQAHwAEAI/wABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDihxJsqTJkyhTqlzJsqXLlzBjypxJs6bNmzhz6tzJs6fPn0CDCh1KtKjRo0iTKl3KtKnTp1CjSp1KtarVq1izat3KtavXr2DDih1LtqzZs2jTql3Ltq3bt3Djyp1Lt67du3jz6t3Lt6/fv4ADCx5MuLDhw4gTK17MuLHjx5AjS55MubLly5gza97MubPnz6BDix5NurTp06hTq17NurXr17Bjy55Nu7bt27hz697Nu7fv38CDCx9OvLjx48iTK1/OvLnz59CjS59Ovbr169iza9/Ovbv37+DDi84fT768+fPo06tfz769+/fw48ufT7++/fv48+vfz7+///8ABijggAQWaOCBCCao4IIMNujggxBGKOGEFFZo4YUYZqjhhhx26OGHIIYo4ogklmjiiSimqOKKLLbo4oswxijjjDTWaOONOOao44489ujjj0AGKeSQRBZp5JFIJqnkkkw26eSTUEYp5ZRUVmnllVhmqeWWXHbp5ZdghinmmGSWaeaZaKap5ppstunmm3DGKeecdNZp55145qnnnnz26eefgAYq6KCEFmrooaQFBAA7")
WEBP = base64.b64decode("UklGRl4AAABXRUJQVlA4IFIAAAAQBgCdASpkAEsAPxGIwFmsKSajoOgBgCIJaQZwZoF4AEuAA9KSxGcQBgEShMHpwnTikgJ0YE6MCXAA/tom/+pO89j7//iF3shqG1G+O6LioAAA")
PNG_VERSION_2 = make_png(color=(196, 82, 59))
CORRUPT_PNG = b"\x89PNG\r\n\x1a\n" + b"not-a-valid-png-chunk"
OVERSIZED_PNG = make_oversized_png()
PNG_DIMENSION_BOMB = (b"\x89PNG\r\n\x1a\n"
                     + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 50000, 50000, 8, 2, 0, 0, 0))
                     + png_chunk(b"IDAT", zlib.compress(b""))
                     + png_chunk(b"IEND", b""))
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
        elif parsed.path == "/slow-shutdown.png":
            # Signal the test harness before sleeping so it can stop NGINX mid-request.
            print("slow shutdown request started", flush=True)
            time.sleep(2.5)
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
            body = (PNG if self.headers.get("Accept") == "text/html"
                    or self.headers.get("Cookie") == "variant=attacker"
                    or self.headers.get("Authorization") == "Bearer attacker"
                    else PNG_VERSION_2)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/sample.jpg":
            body = JPEG
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/sample.gif":
            body = GIF
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/sample.webp":
            body = WEBP
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
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
        elif parsed.path == "/dimension-bomb.png":
            body = PNG_DIMENSION_BOMB
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
