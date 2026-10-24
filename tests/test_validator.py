import struct
import unittest

from validator import validator


def png_header(width, height):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)


def gif_header(width, height):
    return b"GIF89a" + struct.pack("<HH", width, height) + bytes([0, 0, 0]) + b";"


def gif_with_frame(screen_width, screen_height, frame_width, frame_height):
    descriptor = (bytes([0x2C]) + struct.pack("<HHHH", 0, 0, frame_width, frame_height)
                  + bytes([0]))
    image_data = bytes([2, 1, 0, 0])  # LZW code size, one-byte sub-block, terminator.
    return (b"GIF89a" + struct.pack("<HH", screen_width, screen_height)
            + bytes([0, 0, 0]) + descriptor + image_data + b";")


def jpeg_header(width, height):
    # SOI, baseline SOF0 marker, segment length, precision, height, width,
    # and one component. The parser intentionally needs only the frame header.
    return (b"\xff\xd8\xff\xc0" + struct.pack(">H", 8)
            + bytes([8]) + struct.pack(">HH", height, width) + bytes([1]))


class ImageDimensionValidationTests(unittest.TestCase):
    def setUp(self):
        self.old_dimension = validator.MAX_SOURCE_DIMENSION
        self.old_pixels = validator.MAX_SOURCE_PIXELS
        validator.MAX_SOURCE_DIMENSION = 8192
        validator.MAX_SOURCE_PIXELS = 16_777_216

    def tearDown(self):
        validator.MAX_SOURCE_DIMENSION = self.old_dimension
        validator.MAX_SOURCE_PIXELS = self.old_pixels

    def test_reads_png_dimensions_without_decoding_pixels(self):
        self.assertEqual(
            (4000, 3000, "image/png"),
            validator.validate_image(png_header(4000, 3000)),
        )

    def test_reads_gif_dimensions(self):
        self.assertEqual(
            (640, 480, "image/gif"),
            validator.validate_image(gif_header(640, 480)),
        )

    def test_reads_jpeg_dimensions_from_sof(self):
        self.assertEqual(
            (1920, 1080, "image/jpeg"),
            validator.validate_image(jpeg_header(1920, 1080)),
        )

    def test_rejects_source_above_pixel_limit(self):
        with self.assertRaisesRegex(validator.InvalidImage, "pixel limit"):
            validator.validate_image(png_header(5000, 4000))

    def test_rejects_source_above_dimension_limit(self):
        with self.assertRaisesRegex(validator.InvalidImage, "dimension limit"):
            validator.validate_image(gif_header(9000, 100))

    def test_rejects_gif_frame_larger_than_logical_screen(self):
        # A tiny logical screen must not hide a huge per-frame image descriptor.
        with self.assertRaisesRegex(validator.InvalidImage, "dimension limit"):
            validator.validate_image(gif_with_frame(1, 1, 9000, 100))

    def test_rejects_zero_dimensions(self):
        with self.assertRaisesRegex(validator.InvalidImage, "positive"):
            validator.validate_image(png_header(0, 100))

    def test_rejects_unknown_or_truncated_image_headers(self):
        for payload in (b"not an image", b"\x89PNG\r\n\x1a\n", b"\xff\xd8"):
            with self.subTest(payload=payload):
                with self.assertRaises(validator.InvalidImage):
                    validator.validate_image(payload)


if __name__ == "__main__":
    unittest.main()
