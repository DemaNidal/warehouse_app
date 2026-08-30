# -*- coding: utf-8 -*-
"""Image handling: every upload is re-encoded before it is stored.

This is also the only place that checks an upload really is an image, so a
regression here is both a size problem and a security one.
"""

import io

import pytest
from PIL import Image

from utils.images import optimize, optimize_upload, ImageError, MAX_EDGE


def png_bytes(width=400, height=400, mode="RGB"):
    image = Image.new(mode, (width, height), (120, 40, 200) if mode == "RGB" else (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class TestOptimize:

    def test_output_is_webp(self):
        result = optimize(png_bytes())
        assert Image.open(io.BytesIO(result)).format == "WEBP"

    def test_oversized_images_are_scaled_down(self):
        result = optimize(png_bytes(3000, 2000))
        assert max(Image.open(io.BytesIO(result)).size) == MAX_EDGE

    def test_small_images_are_left_at_their_size(self):
        result = optimize(png_bytes(300, 200))
        assert Image.open(io.BytesIO(result)).size == (300, 200)

    def test_aspect_ratio_is_preserved(self):
        result = optimize(png_bytes(3000, 1500))
        width, height = Image.open(io.BytesIO(result)).size
        assert round(width / height, 2) == 2.0

    def test_real_transparency_survives(self):
        # product cut-outs rely on this
        image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        for x in range(100, 300):
            for y in range(100, 300):
                image.putpixel((x, y), (200, 50, 50, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        out = Image.open(io.BytesIO(optimize(buffer)))
        assert out.mode == "RGBA"
        assert out.getchannel("A").getextrema()[0] == 0

    def test_palette_images_are_converted(self):
        image = Image.new("P", (100, 100))
        image.putpalette([0, 0, 0] * 256)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        assert Image.open(io.BytesIO(optimize(buffer))).mode in ("RGB", "RGBA")

    def test_a_large_photo_gets_much_smaller(self):
        original = png_bytes(2400, 2400)
        before = len(original.getvalue())
        original.seek(0)

        assert len(optimize(original)) < before


class TestRejectsNonImages:

    def test_text_pretending_to_be_a_png_is_rejected(self):
        fake = io.BytesIO(b"this is not an image at all")
        with pytest.raises(ImageError):
            optimize(fake)

    def test_empty_file_is_rejected(self):
        with pytest.raises(ImageError):
            optimize(io.BytesIO(b""))


class TestFilenames:

    class _Upload:
        def __init__(self, stream, filename):
            self.stream = stream
            self.filename = filename

    def test_filename_is_unique_and_webp(self):
        first, name_a = optimize_upload(self._Upload(png_bytes(), "photo.png"))
        _, name_b = optimize_upload(self._Upload(png_bytes(), "photo.png"))

        assert name_a.endswith(".webp")
        assert name_a != name_b, "اسمين متطابقين رح يدعسوا بعض بالتخزين"
        assert first

    def test_original_stem_is_kept_for_recognisability(self):
        _, name = optimize_upload(self._Upload(png_bytes(), "soleimer_50ml.png"))
        assert "soleimer_50ml" in name

    def test_a_path_in_the_filename_cannot_escape(self):
        _, name = optimize_upload(self._Upload(png_bytes(), "../../etc/passwd.png"))
        assert "/" not in name and ".." not in name

    def test_missing_file_is_rejected(self):
        with pytest.raises(ImageError):
            optimize_upload(None)
