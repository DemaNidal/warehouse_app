# -*- coding: utf-8 -*-
"""Finding a product from a photograph — the matching itself.

Kept apart from the warehouse application on purpose. Nothing here is
imported by it, nothing here writes to it, and deleting this folder undoes
the whole experiment.

What the measurements said, so the choices here are not arbitrary:

  Cropping to the object first matters. These photos are 1080x1920 of an
  item on a cardboard box, and the standard pipeline centre-crops a square
  after shrinking the short edge — so most of what the model sees is
  cardboard. On the one photo with a known answer, cropping moved the right
  product from rank 11 to rank 7.

  The capacity is invisible. A 250 ml bottle and the same bottle in a litre
  score 0.943 against each other; on that same photo they came back at
  ranks 7 and 8. No amount of tuning separates them, because the difference
  is not in the picture. That is why this returns a shortlist and says so,
  rather than pretending to an answer.
"""

import json
import os

import numpy as np
import onnxruntime as ort
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "model.onnx")
CONFIG = os.path.join(HERE, "preprocessor_config.json")
VECTORS = os.path.join(HERE, "vectors.npz")


def _config():
    with open(CONFIG, encoding="utf-8") as fh:
        config = json.load(fh)
    return (
        config["size"]["shortest_edge"],
        config["crop_size"]["height"],
        np.array(config["image_mean"], dtype=np.float32),
        np.array(config["image_std"], dtype=np.float32),
    )


EDGE, CROP, MEAN, STD = _config()


# ------------------------------------------------------------ preparing

def _to_lab(rgb):
    """sRGB (0-255) to CIELAB, vectorised.

    Used only to find the object: distance in RGB calls a dark brown bottle
    the same as a shadow on cardboard, and that is what the first attempt at
    this got wrong.
    """
    srgb = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92,
                      ((srgb + 0.055) / 1.055) ** 2.4)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = (linear @ matrix.T) / np.array([0.95047, 1.0, 1.08883])
    epsilon, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > epsilon, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.stack([
        116 * f[..., 1] - 16,
        500 * (f[..., 0] - f[..., 1]),
        200 * (f[..., 1] - f[..., 2]),
    ], axis=-1)


def object_box(image, pad=0.06, side=200):
    """Where the item is, by what disagrees with the border colour.

    No segmentation model, and none needed: the backgrounds in these photos
    are one flat cardboard or wall, so the subject is whatever the edges do
    not look like. Returns None when it cannot tell, and the caller then
    falls back to the plain centre crop rather than cropping to noise.
    """
    small = image.convert("RGB").resize((side, side), Image.BILINEAR)
    lab = _to_lab(np.asarray(small, dtype=np.float32))

    edge = max(4, side // 28)
    border = np.concatenate([
        lab[:edge].reshape(-1, 3), lab[-edge:].reshape(-1, 3),
        lab[:, :edge].reshape(-1, 3), lab[:, -edge:].reshape(-1, 3),
    ])
    distance = np.linalg.norm(lab - np.median(border, axis=0), axis=-1)
    mask = distance > max(12.0, float(np.percentile(distance, 70)))

    rows, columns = mask.any(axis=1), mask.any(axis=0)
    if not rows.any() or not columns.any():
        return None

    top, bottom = int(np.argmax(rows)), side - int(np.argmax(rows[::-1]))
    left, right = int(np.argmax(columns)), side - int(np.argmax(columns[::-1]))

    # a "subject" filling the frame means the background was not flat and
    # the guess is worthless
    if (bottom - top) * (right - left) > 0.93 * side * side:
        return None

    width, height = image.size
    sx, sy = width / side, height / side
    box = [left * sx, top * sy, right * sx, bottom * sy]
    padding = pad * max(box[2] - box[0], box[3] - box[1])
    return (
        max(0, box[0] - padding), max(0, box[1] - padding),
        min(width, box[2] + padding), min(height, box[3] + padding),
    )


def _centre_crop(image):
    image = image.convert("RGB")
    width, height = image.size
    scale = EDGE / min(width, height)
    image = image.resize(
        (round(width * scale), round(height * scale)), Image.BICUBIC
    )
    width, height = image.size
    left, top = (width - CROP) // 2, (height - CROP) // 2
    return image.crop((left, top, left + CROP, top + CROP))


def prepare(image, crop_to_object=True):
    """Returns the tensor and whether the object was found."""
    found = False
    if crop_to_object:
        box = object_box(image)
        if box is not None:
            image = image.crop(tuple(int(v) for v in box))
            found = True

    pixels = np.asarray(_centre_crop(image), dtype=np.float32) / 255.0
    pixels = (pixels - MEAN) / STD
    return pixels.transpose(2, 0, 1), found


# ------------------------------------------------------------- the model

class Finder:
    """Loads once. The weights are 352 MB and the process settles near
    400 MB, so this is built at startup and reused, never per request."""

    def __init__(self):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        self.session = ort.InferenceSession(
            MODEL, options, providers=["CPUExecutionProvider"]
        )
        self.input = self.session.get_inputs()[0].name
        self.output = self.session.get_outputs()[0].name

        data = np.load(VECTORS)
        self.ids = [int(i) for i in data["ids"]]
        self.index = data["vectors"]

    def encode(self, image, crop_to_object=True):
        tensor, found = prepare(image, crop_to_object)
        vector = self.session.run(
            [self.output], {self.input: tensor[None]}
        )[0][0]
        if vector.ndim > 1:
            vector = vector[0]
        return vector / np.linalg.norm(vector), found

    def search(self, image, limit=12, crop_to_object=True):
        vector, found = self.encode(image, crop_to_object)
        scores = self.index @ vector
        order = np.argsort(-scores)[:limit]
        return (
            [(self.ids[i], float(scores[i])) for i in order],
            found,
        )
