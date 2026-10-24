from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import struct
import zlib

def png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

def make_png(width=320, height=240):
    row = b"\\x00" + (b"\\x3b\\x82\\xc4" * width)
    raw = row * height
    return (b"\\x89PNG\\r\\n\\x1a\\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw))
            + png_chunk(b"IEND", b""))

PNG = make_png()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sample.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
        elif self.path == "/not-an-image.png":
            body = b"this is not an image"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
