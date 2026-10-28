"""Crop photographs, either from boxes drawn in the web editor or by centring on an aspect ratio."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional

from PIL import Image

from .burnin import _check_output, _destination, _open_oriented, _output_params, save_image
from .common import (BURNIN_IMAGE_EXTS, Cancelled, Context, Item, Operation, OperationError, Param, Plan,
                     Reporter)

MIN_SIDE = 8  # pixels
EXIF_IFD = 0x8769
PIXEL_X, PIXEL_Y = 40962, 40963  # Exif.Photo.PixelXDimension / PixelYDimension
ORIENTATION = 0x0112


def parse_ratio(text) -> Optional[float]:
    """'3:2', '3x2' or '1.5' -> width/height; blank -> None."""
    text = str(text or "").strip().lower().replace(" ", "")
    if not text:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)[:x/](\d+(?:\.\d+)?)", text) or re.fullmatch(r"(\d+(?:\.\d+)?)()", text)
    if not m:
        raise OperationError("Enter the aspect ratio as width:height, e.g. 3:2 or 16:9.")
    w, h = float(m.group(1)), float(m.group(2) or 1)
    if w <= 0 or h <= 0:
        raise OperationError("The aspect ratio must be greater than zero.")
    return w / h


def oriented_size(path: Path) -> tuple:
    """Pixel size of the image as displayed (after applying the EXIF orientation)."""
    with Image.open(path) as im:
        w, h = im.size
        if im.getexif().get(ORIENTATION) in (5, 6, 7, 8):
            w, h = h, w
    return w, h


def centred_box(size: tuple, ratio: float) -> tuple:
    """Largest box with the given width/height ratio centred in an image of `size`."""
    width, height = size
    if width / height > ratio:
        w, h = max(1, round(height * ratio)), height
    else:
        w, h = width, max(1, round(width / ratio))
    x0, y0 = (width - w) // 2, (height - h) // 2
    return x0, y0, x0 + w, y0 + h


def pixel_box(fraction, size: tuple) -> tuple:
    """Convert [x, y, w, h] fractions of the image to a validated pixel box (x0, y0, x1, y1)."""
    try:
        x, y, w, h = (float(v) for v in fraction)
    except (TypeError, ValueError):
        raise OperationError("Crop box must be four numbers.") from None
    if not all(math.isfinite(v) for v in (x, y, w, h)) or min(x, y) < -1e-6 or w <= 0 or h <= 0 \
            or x + w > 1 + 1e-6 or y + h > 1 + 1e-6:
        raise OperationError("Crop box lies outside the image.")
    width, height = size
    x0, y0 = max(0, round(x * width)), max(0, round(y * height))
    x1, y1 = min(width, round((x + w) * width)), min(height, round((y + h) * height))
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        raise OperationError(f"Crop box is too small (minimum {MIN_SIDE} pixels).")
    return x0, y0, x1, y1


def _updated_exif(exif_bytes, size: tuple):
    """Keep the EXIF block but refresh stale pixel dimensions."""
    if not exif_bytes:
        return exif_bytes
    try:
        exif = Image.Exif()
        exif.load(exif_bytes)
        ifd = exif.get_ifd(EXIF_IFD)
        if PIXEL_X in ifd:
            ifd[PIXEL_X] = size[0]
        if PIXEL_Y in ifd:
            ifd[PIXEL_Y] = size[1]
        return exif.tobytes()
    except Exception:
        return exif_bytes


def plan_crop(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    _check_output(params)
    default_ratio = parse_ratio(params.get("ratio"))
    crops = params.get("crops") or {}
    plan = Plan(op="crop")
    payload = []
    for src in files:
        if src.suffix.lower() not in BURNIN_IMAGE_EXTS:
            plan.items.append(Item(str(src), None, "crop", "skip", "format not supported for cropping"))
            continue
        rel = ctx.rel(src)
        if rel not in crops and default_ratio is None:
            plan.items.append(Item(str(src), None, "crop", "skip", "no crop set"))
            continue
        try:
            size = oriented_size(src)
            box = pixel_box(crops[rel], size) if rel in crops else centred_box(size, default_ratio)
        except OperationError as exc:
            plan.items.append(Item(str(src), None, "crop", "error", str(exc)))
            continue
        except Exception as exc:
            plan.items.append(Item(str(src), None, "crop", "error", f"cannot read image: {exc}"))
            continue
        dst = _destination(ctx, src, params)
        new_w, new_h = box[2] - box[0], box[3] - box[1]
        note = f"{size[0]}×{size[1]} → {new_w}×{new_h}"
        item = Item(str(src), str(dst), "crop", "ok", note)
        if not params.get("overwrite") and src.resolve() == dst.resolve():
            item.status = "error"
            item.note = "output would replace the original; tick overwrite or pick another folder"
            plan.errors.append("The output folder is the same as the source folder. Tick 'Overwrite the "
                               "original files' or choose a different output folder.")
        elif params.get("overwrite"):
            item.note += "; original will be replaced"
        elif dst.exists():
            item.note += "; replaces an existing file in the output folder"
        plan.items.append(item)
        if item.status == "ok":
            payload.append((src, dst, box))
    plan.errors = list(dict.fromkeys(plan.errors))
    plan.payload = payload
    plan.summary = f"{len(payload)} of {len(plan.items)} photo(s) will be cropped."
    if params.get("overwrite") and payload:
        plan.warnings.append("Originals will be permanently replaced with the cropped version.")
    n_err = sum(1 for i in plan.items if i.status == "error")
    if n_err and not plan.errors:
        plan.warnings.append(f"{n_err} photo(s) have a problem and will be skipped.")
    return plan


def apply_crop(ctx: Context, plan: Plan, rep: Reporter) -> None:
    rep.start(len(plan.payload))
    for src, dst, box in plan.payload:
        rep.begin_item(src.name)
        try:
            img = _open_oriented(src)
            exif, icc = img.info.get("exif"), img.info.get("icc_profile")
            cropped = img.crop(box)
            save_image(cropped, dst, _updated_exif(exif, cropped.size), icc)
            rep.ok(f"{src.name} -> {ctx.rel(dst)} ({cropped.width}×{cropped.height})")
        except Cancelled:
            raise
        except Exception as exc:
            rep.failed(f"{src.name}: {exc}")
        rep.end_item()


OPERATIONS = [
    Operation(
        id="crop", label="Crop photographs", group="photos", editor="crop",
        description="Draw a crop box on each photograph, freeform or locked to an aspect ratio. "
                    "Photos you leave uncropped are skipped.",
        params=[
            Param("ratio", "Centre-crop remaining photos to ratio", "text",
                  help="Optional, e.g. 3:2 or 16:9. Photos without a hand-drawn crop are cropped around their "
                       "centre to this ratio. In the terminal menu this is the only way to crop."),
            *_output_params(),
        ],
        plan=plan_crop, apply=apply_crop, accepts=("image",),
    ),
]
