"""Turn an uploaded file into a web-sized image.

Product photos arrive straight from a phone or a supplier: the catalogue has
PNGs at 2.7 MB on average and one at 78 MB. Nobody needs that — the largest
place an image is shown is the zoom modal on the product page — so every
upload is resized and re-encoded to WebP before it is stored.

Doing it on the way in matters more than fixing what is already there: the
next thousand products would otherwise add ~2.7 GB of the same problem.
"""

import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename


# Longest edge, in pixels. The zoom modal is the biggest consumer and it is
# capped by the viewport, so this is generous rather than tight.
MAX_EDGE = 1200

# WebP quality. 82 is visually indistinguishable from the source for product
# shots on a flat background while cutting size by roughly 95%.
QUALITY = 82

OUTPUT_EXTENSION = "webp"

# Pillow refuses very large images as a decompression-bomb guard. The 78 MB
# PNG in this catalogue is a legitimate (if silly) product photo, so allow
# more than the default while still keeping a ceiling.
Image.MAX_IMAGE_PIXELS = 300_000_000


class ImageError(Exception):
    """The upload was not a usable image."""


def _build_filename(original_name):
    """uuid_originalstem.webp — unique, so a stored name is never reused."""

    stem = secure_filename(original_name or "image")
    stem = stem.rsplit(".", 1)[0] or "image"

    return f"{uuid.uuid4()}_{stem}.{OUTPUT_EXTENSION}"


def optimize(source, max_edge=MAX_EDGE, quality=QUALITY):
    """Return WebP bytes for `source` (a path or a file-like object).

    Raises ImageError if the bytes are not an image Pillow can read — which
    also means an upload is validated by actually decoding it, not by trusting
    its file extension.
    """

    try:
        image = Image.open(source)
        image.load()
    except UnidentifiedImageError:
        raise ImageError("الملف مش صورة صالحة")
    except Image.DecompressionBombError:
        raise ImageError("الصورة كبيرة بشكل غير معقول")
    except Exception as exc:
        raise ImageError(f"تعذّرت قراءة الصورة: {exc}")

    # Phone photos carry rotation in EXIF; bake it in so the stored file is
    # already the right way up.
    image = ImageOps.exif_transpose(image)

    # WebP handles RGB and RGBA. Palette and CMYK sources need converting, and
    # transparency has to survive the trip — most of these are cut-outs.
    if image.mode in ("P", "LA"):
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    if max(image.size) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)

    return buffer.getvalue()


def optimize_upload(file_storage, max_edge=MAX_EDGE, quality=QUALITY):
    """Optimise a Werkzeug FileStorage. Returns (bytes, filename)."""

    if not file_storage or not file_storage.filename:
        raise ImageError("ما في ملف مرفوع")

    file_storage.stream.seek(0)
    data = optimize(file_storage.stream, max_edge=max_edge, quality=quality)

    return data, _build_filename(file_storage.filename)
