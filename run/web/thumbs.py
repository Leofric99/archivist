"""Thumbnail and preview generation, all done locally from the files on disk."""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from ..core.common import PYEXIV2_LOCK, kind_of

try:  # Optional: lets Pillow open HEIC/HEIF files.
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass


def _to_jpeg(img: Image.Image, quality: int) -> bytes:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _from_pillow(path: Path, size: int, quality: int) -> Optional[bytes]:
    try:
        with Image.open(path) as im:
            im.draft("RGB", (size, size))
            im = ImageOps.exif_transpose(im)
            im.thumbnail((size, size))
            return _to_jpeg(im, quality)
    except Exception:
        return None


def _from_embedded(path: Path, size: int, quality: int) -> Optional[bytes]:
    """Use the preview JPEG embedded in RAW files."""
    try:
        import pyexiv2
        with PYEXIV2_LOCK, pyexiv2.Image(str(path)) as meta:
            data = meta.read_thumbnail()
        if not data:
            return None
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((size, size))
            return _to_jpeg(im, quality)
    except Exception:
        return None


def _from_sips(path: Path, size: int) -> Optional[bytes]:
    """macOS can decode HEIC and many RAW formats through the built-in sips tool."""
    if not shutil.which("sips"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "thumb.jpg"
        try:
            subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(size), str(path), "--out", str(out)],
                           capture_output=True, timeout=60, check=True)
            return out.read_bytes()
        except Exception:
            return None


def _from_video(path: Path, size: int) -> Optional[bytes]:
    if not shutil.which("ffmpeg"):
        return None
    for seek in ("1", "0"):
        try:
            result = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", seek, "-i", str(path), "-frames:v", "1",
                 "-vf", f"scale='min({size},iw)':-2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                capture_output=True, timeout=60)
            if result.stdout:
                return result.stdout
        except Exception:
            return None
    return None


def make_image(path: Path, size: int, quality: int = 80) -> Optional[bytes]:
    kind = kind_of(path)
    if kind == "video":
        return _from_video(path, size)
    data = _from_pillow(path, size, quality)
    if data is None and kind in ("image", "raw"):
        data = _from_embedded(path, size, quality) or _from_sips(path, size)
    return data


class ThumbnailCache:
    """Disk cache in a temp folder keyed by path, modification time and size."""

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="archivist-thumbs-"))

    def get(self, path: Path, size: int, quality: int = 80) -> Optional[bytes]:
        st = path.stat()
        key = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{st.st_size}|{size}".encode()).hexdigest()
        cached = self.dir / f"{key}.jpg"
        if cached.exists():
            return cached.read_bytes()
        data = make_image(path, size, quality)
        if data:
            cached.write_bytes(data)
        return data

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
