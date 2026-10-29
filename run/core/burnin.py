"""Burn dates and captions into photographs and videos."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import FONT
from . import fonts
from .common import (BURNIN_IMAGE_EXTS, Cancelled, Context, Item, Operation, OperationError, Param,
                     Plan, Reporter, kind_of, to_path)
from .dates import format_custom_date, format_datetime, photo_date, validate_date_string, video_date

FONT_PATH = fonts.FONT_DIR / FONT


def load_font(size: int):
    """The fixed Arial used by the date burn-in (looked up relative to the package, not the cwd)."""
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


# ---- Photo rendering ----


def _open_oriented(path: Path, max_side: Optional[int] = None) -> Image.Image:
    with Image.open(path) as im:
        if max_side:
            im.draft("RGB", (max_side, max_side))
            im.thumbnail((max_side, max_side))
        return ImageOps.exif_transpose(im)


def render_basic(path: Path, text: str, custom_date: str, max_side: Optional[int] = None):
    """Date (plus optional text) in the bottom-right corner. Returns (image, exif bytes, icc profile)."""
    img = _open_oriented(path, max_side).convert("RGBA")
    exif, icc = img.info.get("exif"), img.info.get("icc_profile")
    stamp = format_custom_date(custom_date) if custom_date else format_datetime(photo_date(path))
    display = f"{stamp}{f' | {text}' if text else ''}"
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    small = min(img.size)
    font_size = max(8, int(small * 0.045))
    font = load_font(font_size)
    box = draw.textbbox((0, 0), display, font=font)
    margin = int(small * 0.01)
    pos = (img.width - (box[2] - box[0]) - margin, img.height - (box[3] - box[1]) - margin)
    reach = max(1, round(font_size / 24))
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            if dx or dy:
                draw.text((pos[0] + dx, pos[1] + dy), display, font=font, fill=(0, 0, 0, 255))
    draw.text(pos, display, font=font, fill=(255, 255, 255, 160))
    return Image.alpha_composite(img, overlay).convert("RGB"), exif, icc


CAPTION_SCALE = 1.5  # caption text size relative to the original 1.5%-of-height size


def render_caption(path: Path, caption: str, max_side: Optional[int] = None, font_name: Optional[str] = None):
    """Caption on a white band added below the image. Returns (image, exif bytes, icc profile)."""
    img = _open_oriented(path, max_side).convert("RGB")
    exif, icc = img.info.get("exif"), img.info.get("icc_profile")
    base_size = max(8, int(img.height * 0.015))
    font_size = round(base_size * CAPTION_SCALE)
    font = fonts.load_font(font_name, font_size)
    draw = ImageDraw.Draw(img)
    # The strip keeps its original single-line height; the larger text is centred within it. The gap above and
    # below the text (`pad`) is also the minimum gap left and right, so lines fill the width before wrapping.
    base_lh = draw.textbbox((0, 0), "A", font=fonts.load_font(font_name, base_size))[3]
    strip = base_lh + base_size
    # Tallest ascender/bracket and deepest descender, so the visible gap really is `pad` all round.
    top, bottom = draw.textbbox((0, 0), "Aly(|gjpqy)", font=font)[1::2]
    ink = bottom - top
    pitch = bottom + max(1, font_size // 8)
    pad = max(2, (strip - ink) // 2)
    max_width = max(1, img.width - 2 * pad)

    def ink_width(text: str) -> int:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        return right - left

    lines, line = [], ""
    for word in caption.split():
        test = f"{line} {word}".strip()
        if ink_width(test) <= max_width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    band = (len(lines) - 1) * pitch + ink + 2 * pad
    out = Image.new("RGB", (img.width, img.height + band), (255, 255, 255))
    out.paste(img, (0, 0))
    draw = ImageDraw.Draw(out)
    y = img.height + pad - top
    for text in lines:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        draw.text(((out.width - (right - left)) // 2 - left, y), text, font=font, fill=(0, 0, 0))
        y += pitch
    return out, exif, icc


def save_image(img: Image.Image, dst: Path, exif=None, icc=None) -> None:
    """Save atomically (temp file + replace), keeping EXIF and colour profile where possible."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = Image.registered_extensions().get(dst.suffix.lower())
    tmp = dst.with_name(f".{dst.stem}.archivist-tmp{dst.suffix}")
    kwargs = {}
    if fmt == "JPEG":
        kwargs["quality"] = 95
    if icc:
        kwargs["icc_profile"] = icc
    try:
        try:
            img.save(tmp, format=fmt, **({"exif": exif} if exif else {}), **kwargs)
        except Exception:
            img.save(tmp, format=fmt, **kwargs)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


# ---- Planning shared by photo and video burn-in ----


def _font_choices() -> list:
    return [[name, name] for name in fonts.font_names()]


def _output_params() -> list:
    return [
        Param("overwrite", "Overwrite the original files", "bool", default=False,
              help="Off by default. When off, results are written to the output folder and originals are untouched."),
        Param("output_dir", "Output folder", "path", show_if={"overwrite": False},
              help="Created if missing. For dropped photos, leave blank to save a new copy beside each original."),
    ]


def _destination(ctx: Context, src: Path, params: dict) -> Path:
    if params.get("overwrite"):
        return src
    if ctx.tracked_files is not None:
        if not (params.get("output_dir") or "").strip():
            return src.with_name(f"{src.stem}_archivist{src.suffix}")
        return to_path(params["output_dir"]) / src.name
    out_dir = to_path(params.get("output_dir", ""))
    rel = Path(ctx.rel(src))
    return out_dir / (rel if not rel.is_absolute() else Path(src.name))


def _check_output(params: dict, ctx: Optional[Context] = None) -> None:
    if not params.get("overwrite") and not (params.get("output_dir") or "").strip() \
            and not (ctx and ctx.tracked_files is not None):
        raise OperationError("Choose an output folder, or tick 'Overwrite the original files'.")


def _text_for(ctx: Context, src: Path, params: dict, required_caption: bool) -> Optional[str]:
    captions = params.get("captions") or {}
    own = (captions.get(ctx.rel(src)) or "").strip()
    if required_caption:
        return own or None
    return own or (params.get("text") or "").strip()


def _plan_burnin(ctx: Context, files: list, params: dict, op: str, media_kind: str,
                 required_caption: bool = False) -> Plan:
    _check_output(params, ctx)
    custom_date = (params.get("custom_date") or "").strip()
    if custom_date:
        try:
            custom_date = validate_date_string(custom_date)
        except ValueError as exc:
            raise OperationError(str(exc))
    plan = Plan(op=op)
    payload = []
    destinations = set()
    for src in files:
        if media_kind == "image" and src.suffix.lower() not in BURNIN_IMAGE_EXTS:
            plan.items.append(Item(str(src), None, "burn-in", "skip", "format not supported for burn-in"))
            continue
        if media_kind == "video" and kind_of(src) != "video":
            plan.items.append(Item(str(src), None, "burn-in", "skip", "not a video"))
            continue
        text = _text_for(ctx, src, params, required_caption)
        if text is None:
            plan.items.append(Item(str(src), None, "burn-in", "skip", "no caption entered"))
            continue
        dst = _destination(ctx, src, params)
        item = Item(str(src), str(dst), "burn-in", "ok")
        if dst.resolve() in destinations:
            item.status, item.note = "error", "another selected file has the same output name"
        elif not params.get("overwrite") and src.resolve() == dst.resolve():
            item.status, item.note = "error", "output would replace the original; tick overwrite or pick another folder"
        elif params.get("overwrite"):
            item.note = "original will be replaced"
        elif dst.exists():
            item.note = "replaces an existing file in the output folder"
        destinations.add(dst.resolve())
        plan.items.append(item)
        if item.status == "ok":
            payload.append((src, dst, text, custom_date))
    n_err = sum(1 for i in plan.items if i.status == "error")
    if n_err:
        if any("same output name" in item.note for item in plan.items):
            plan.errors.append("Multiple selected files would use the same output name. Choose a different output folder.")
        else:
            plan.errors.append("The output folder is the same as the source folder. Tick 'Overwrite the original "
                               "files' or choose a different output folder.")
    plan.payload = payload
    plan.summary = f"{len(payload)} of {len(plan.items)} file(s) will be processed."
    if params.get("overwrite") and payload:
        plan.warnings.append("Originals will be permanently replaced.")
    return plan


def plan_basic(ctx, files, params, answers):
    return _plan_burnin(ctx, files, params, "burnin_basic", "image")


def _chosen_font(params: dict) -> str:
    name = (params.get("font") or "").strip() or fonts.default_font_name()
    if name not in fonts.available_fonts():
        raise OperationError(f"Unknown font: {name}")
    return name


def plan_caption(ctx, files, params, answers):
    font_name = _chosen_font(params)
    plan = _plan_burnin(ctx, files, params, "burnin_caption", "image", required_caption=True)
    plan.options["font"] = font_name
    return plan


def plan_video(ctx, files, params, answers):
    plan = _plan_burnin(ctx, files, params, "burnin_video", "video")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        plan.errors.append("ffmpeg and ffprobe must be installed and on your PATH to process videos.")
    plan.warnings.append("Video re-encoding can take a long time; progress is shown per file.")
    return plan


def _apply_images(renderer):
    def apply(ctx: Context, plan: Plan, rep: Reporter) -> None:
        rep.start(len(plan.payload))
        for src, dst, text, custom_date in plan.payload:
            rep.begin_item(src.name)
            try:
                img, exif, icc = renderer(src, text, custom_date)
                save_image(img, dst, exif, icc)
                rep.ok(f"{src.name} -> {ctx.rel(dst)}")
            except Cancelled:
                raise
            except Exception as exc:
                rep.failed(f"{src.name}: {exc}")
            rep.end_item()
    return apply


apply_basic = _apply_images(lambda src, text, date: render_basic(src, text, date))
def apply_caption(ctx: Context, plan: Plan, rep: Reporter) -> None:
    font_name = plan.options.get("font")
    _apply_images(lambda src, text, date: render_caption(src, text, font_name=font_name))(ctx, plan, rep)


def preview_basic(ctx: Context, path: Path, params: dict, caption: Optional[str]):
    text = (caption or params.get("text") or "").strip()
    return render_basic(path, text, (params.get("custom_date") or "").strip(), max_side=1400)[0]


def preview_caption(ctx: Context, path: Path, params: dict, caption: Optional[str]):
    sample = (caption or "Example caption text").strip()
    return render_caption(path, sample, max_side=1400, font_name=_chosen_font(params))[0]


# ---- Video ----


def _probe_video(path: Path) -> tuple:
    """Return (height, duration seconds) with None for anything unknown."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60).stdout
        data = json.loads(out or "{}")
        height = (data.get("streams") or [{}])[0].get("height")
        duration = float((data.get("format") or {}).get("duration") or 0) or None
        return height, duration
    except Exception:
        return None, None


def render_video_overlay(text: str, video_height: Optional[int]) -> Image.Image:
    """Transparent PNG with the text on a translucent box; avoids needing ffmpeg's drawtext filter."""
    font_size = max(24, round((video_height or 0) * 0.03))
    font = load_font(font_size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font, stroke_width=2)
    pad = max(5, font_size // 5)
    img = Image.new("RGBA", (box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad), (0, 0, 0, 102))
    ImageDraw.Draw(img).text((pad - box[0], pad - box[1]), text, font=font, fill=(255, 255, 255, 255),
                             stroke_width=2, stroke_fill=(0, 0, 0, 180))
    return img


def _hw_encoder() -> Optional[str]:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                             text=True, check=True, timeout=30).stdout
    except Exception:
        return None
    for name in ("h264_nvenc", "h264_qsv", "h264_amf"):
        if name in out:
            return name
    return None


def _run_ffmpeg(cmd: list, duration: Optional[float], rep: Reporter) -> tuple:
    """Run ffmpeg reporting progress; returns (returncode, stderr text). Raises Cancelled."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        try:
            for line in proc.stdout:
                rep.check()
                key, _, value = line.strip().partition("=")
                if key in ("out_time_us", "out_time_ms") and duration:
                    try:
                        rep.item_progress(int(value) / 1_000_000 / duration)
                    except ValueError:
                        pass
        except Cancelled:
            proc.terminate()
            proc.wait()
            raise
        finally:
            if proc.poll() is None:
                proc.wait()
        err.seek(0)
        return proc.returncode, err.read().decode(errors="replace")[-600:]


def apply_video(ctx: Context, plan: Plan, rep: Reporter) -> None:
    hw = _hw_encoder()
    rep.start(len(plan.payload))
    for src, dst, text, custom_date in plan.payload:
        rep.begin_item(src.name)
        stamp = format_custom_date(custom_date) if custom_date else format_datetime(video_date(src))
        display = f"{stamp}{f' | {text}' if text else ''}"
        height, duration = _probe_video(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = dst.with_name(f".{dst.stem}.archivist-tmp{dst.suffix}")
        fd, overlay_name = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_video_overlay(display, height).save(overlay_name)
            returncode, stderr = 1, ""
            for codec in ([hw] if hw else []) + ["libx264"]:
                cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
                       "-i", str(src), "-i", overlay_name,
                       "-filter_complex", "[0:v][1:v]overlay=W-w-20:H-h-20[v]",
                       "-map", "[v]", "-map", "0:a?", "-map_metadata", "0",
                       "-c:v", codec, "-c:a", "copy", str(tmp_out)]
                returncode, stderr = _run_ffmpeg(cmd, duration, rep)
                if returncode == 0:
                    break
                if codec != "libx264":
                    rep.log(f"{codec} failed for {src.name}; retrying with libx264.", "warn")
            if returncode != 0:
                raise RuntimeError(stderr.strip() or f"ffmpeg exited with {returncode}")
            os.replace(tmp_out, dst)
            rep.ok(f"{src.name} -> {ctx.rel(dst)}")
        except Cancelled:
            raise
        except Exception as exc:
            rep.failed(f"{src.name}: {exc}")
        finally:
            for leftover in (tmp_out, Path(overlay_name)):
                if leftover.exists():
                    leftover.unlink()
        rep.end_item()


CUSTOM_DATE = Param("custom_date", "Custom date", "date",
                    help="Optional. YYYYMMDD, YYYYMM or YYYY. Leave blank to use the date found in the file.")

OPERATIONS = [
    Operation(
        id="burnin_basic", label="Burn in date and text", group="photos",
        description="Draws the date (and optional text) in the bottom-right corner of each photograph.",
        params=[Param("text", "Text to add after the date", "text",
                      help="Applied to every selected photo unless you enter a per-photo caption below."),
                CUSTOM_DATE, *_output_params()],
        plan=plan_basic, apply=apply_basic, accepts=("image",), captions="optional", preview=preview_basic,
    ),
    Operation(
        id="burnin_caption", label="Burn in captions (verbose)", group="photos",
        description="Adds a white band below each photograph containing its own caption. "
                    "Photos with an empty caption are skipped.",
        params=[Param("font", "Font", "choice", choices_fn=_font_choices, default_fn=fonts.default_font_name,
                      help="Any font installed on this computer. Use Preview to see how it looks."),
                *_output_params()],
        plan=plan_caption, apply=apply_caption, accepts=("image",), captions="required", preview=preview_caption,
    ),
    Operation(
        id="burnin_video", label="Burn in date and text", group="videos",
        description="Overlays the date (and optional text) on each video. Requires ffmpeg. "
                    "Videos are re-encoded, which can take a while.",
        params=[Param("text", "Text to add after the date", "text"), CUSTOM_DATE, *_output_params()],
        plan=plan_video, apply=apply_video, accepts=("video",), captions="optional",
    ),
]
