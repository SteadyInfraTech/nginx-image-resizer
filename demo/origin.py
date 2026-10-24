from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import struct
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/sample.png":
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

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
