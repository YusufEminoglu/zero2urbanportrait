# -*- coding: utf-8 -*-
"""Free the urban-portrait relief from its medallion.

    git show 5a8225f:icons/icon.png > medallion.png
    py -3 dev/icon_lab/cutout.py medallion.png icons/icon.png

The 0.4.2 artwork is a round medallion: a coral/teal rim around a light-grey
plate, with the face and the city carved on it. The plate and the rim are the
icon's background and frame; this keeps only the carving. The plate is found by
flood-filling its low-saturation grey from seeds behind the face, the rim by a
circle fitted to its inner bevel. Edge pixels are un-mixed from the plate grey
so no light fringe survives, then the result is cropped to its drawn pixels
with a level bust cut at the bottom, so it fills a transparent 512 px square
edge to edge.
Development only; dev/ is not part of the plugin zip.
"""
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

# Inner edge of the rim's bevel; the medallion is seen slightly from below,
# so the carving's centre sits above the image centre.
CIRCLE = (256.0, 248.0, 228.0)
PLATE_SEEDS = ((470, 256), (440, 150), (430, 330), (400, 80), (330, 455))
PLATE_GREY = np.array([212.0, 208.0, 203.0])


def saturation(rgb):
    high, low = rgb.max(-1), rgb.min(-1)
    return np.where(high > 0, (high - low) / np.maximum(high, 1e-6), 0.0)


def flood(candidate, seeds):
    h, w = candidate.shape
    seen = np.zeros_like(candidate)
    queue = deque((y, x) for x, y in seeds if candidate[y, x])
    for y, x in queue:
        seen[y, x] = True
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                queue.append((ny, nx))
    return seen


def main(source, target, size=512):
    image = np.array(Image.open(source).convert("RGBA")).astype(float)
    rgb, alpha = image[..., :3], image[..., 3] / 255.0
    sat = saturation(rgb / 255.0)
    h, w = sat.shape
    yy, xx = np.mgrid[0:h, 0:w]

    # The plate: connected low-saturation grey behind the face.
    plate = flood((sat < 0.09) & (alpha > 0.5), PLATE_SEEDS)
    near = np.array(Image.fromarray((plate * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    # Soft matte at the plate border: grey reads as plate, warm tan as carving.
    soft = np.clip((sat - 0.06) / 0.06, 0.0, 1.0)
    matte = np.where(plate, 0.0, np.where(near, soft, 1.0))
    matte = np.array(Image.fromarray((matte * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))) / 255.0

    # The rim: outside the bevel circle, with a one-pixel feather.
    cx, cy, radius = CIRCLE
    ring = np.clip(radius + 0.5 - np.hypot(xx - cx, yy - cy), 0.0, 1.0)
    out_alpha = alpha * matte * ring
    # Keep only the carving itself: specks of rim or plate shadow that survive
    # the thresholds are separate islands, and one would widen the crop.
    solid = out_alpha > 0.5
    body = flood(solid, ((140, 250), (380, 250)))
    # A clean contour along the face: blur the solid mask and re-threshold it
    # with a narrow ramp, which removes stair-steps and the plate's grey lip.
    mask = Image.fromarray((body * 255).astype(np.uint8))
    opened = np.array(mask.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))) > 0
    body = np.where(near, opened & body, body)
    blurred = np.array(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1))) / 255.0
    contour = np.clip((blurred - 0.55) * 2.6 + 0.5, 0.0, 1.0)
    out_alpha = np.where(near, np.minimum(contour, ring) * alpha, out_alpha * (blurred > 0.02))

    # Un-mix the plate grey from partially covered edge pixels.
    a = np.clip(out_alpha / np.maximum(alpha, 1e-6), 1e-3, 1.0)[..., None]
    edge = (out_alpha > 0) & (out_alpha < alpha - 1e-3)
    clean = np.clip((rgb - (1.0 - a) * PLATE_GREY) / a, 0, 255)
    rgb = np.where(edge[..., None] & near[..., None], clean, rgb)

    result = np.dstack([rgb, out_alpha * 255.0]).round().astype(np.uint8)
    picture = Image.fromarray(result, "RGBA")
    ys, xs = np.nonzero(result[..., 3] > 6)
    # The carving is taller than wide; a level bust cut at the bottom makes it
    # square, so it touches all four edges (no margin on either axis).
    side = xs.max() + 1 - xs.min()
    top = ys.min()
    picture = picture.crop((xs.min(), top, xs.max() + 1, top + side))
    picture.resize((size, size), Image.LANCZOS).save(target)
    print("crop", picture.size, "->", size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
