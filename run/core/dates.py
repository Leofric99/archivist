"""Date detection and formatting shared by renaming and burn-in operations."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ExifTags

from .common import PYEXIV2_LOCK, kind_of

EXIF_IFD = 0x8769
_EXIF_DATE_NAMES = ("DateTimeOriginal", "DateTimeDigitized")
_PYEXIV2_DATE_KEYS = ("Exif.Photo.DateTimeOriginal", "Exif.Photo.DateTimeDigitized", "Exif.Image.DateTime")


def format_datetime(dt: Optional[datetime]) -> str:
    """e.g. '1st January 2020'."""
    if not dt:
        return ""
    n = dt.day
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} {dt.strftime('%B')} {dt.year}"


def format_custom_date(date_str: Optional[str]) -> str:
    """Format a YYYYMMDD / YYYYMM / YYYY string for display."""
    if not date_str:
        return ""
    try:
        if re.fullmatch(r"\d{8}", date_str):
            return format_datetime(datetime.strptime(date_str, "%Y%m%d"))
        if re.fullmatch(r"\d{6}", date_str):
            dt = datetime.strptime(date_str, "%Y%m")
            return f"{dt.strftime('%B')} {dt.year}"
    except ValueError:
        pass
    return date_str


def validate_date_string(value: str, lengths=(4, 6, 8)) -> str:
    """Return a cleaned YYYY / YYYYMM / YYYYMMDD string or raise ValueError."""
    text = (value or "").strip()
    if not text.isdigit() or len(text) not in lengths:
        names = {4: "YYYY", 6: "YYYYMM", 8: "YYYYMMDD"}
        raise ValueError("Enter the date as " + " or ".join(names[n] for n in lengths) + ".")
    padded = text + {4: "0101", 6: "01", 8: ""}[len(text)]
    try:
        datetime.strptime(padded, "%Y%m%d")
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date.") from None
    return text


def _date_from_name(name: str) -> Optional[datetime]:
    m = re.search(r"(\d{8})[_\-]?(\d{6})", name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    m = re.search(r"(\d{8})", name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            pass
    return None


def _parse_exif_date(value) -> Optional[datetime]:
    text = value.decode(errors="ignore") if isinstance(value, bytes) else str(value)
    text = text.strip().rstrip("\x00")
    for fmt in ("%Y:%m:%d %H:%M:%S.%f", "%Y:%m:%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _pillow_exif_date(path: Path) -> Optional[datetime]:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            merged = dict(exif)
            merged.update(exif.get_ifd(EXIF_IFD))
    except Exception:
        return None
    named = {ExifTags.TAGS.get(k, k): v for k, v in merged.items()}
    for key in _EXIF_DATE_NAMES:
        if key in named:
            dt = _parse_exif_date(named[key])
            if dt:
                return dt
    return None


def _pyexiv2_date(path: Path) -> Optional[datetime]:
    try:
        import pyexiv2
        with PYEXIV2_LOCK, pyexiv2.Image(str(path)) as img:
            data = img.read_exif()
    except Exception:
        return None
    for key in _PYEXIV2_DATE_KEYS:
        if key in data:
            dt = _parse_exif_date(data[key])
            if dt:
                return dt
    return None


def photo_date(path: Path) -> datetime:
    """EXIF capture date, else a date in the file name, else the modification time."""
    path = Path(path)
    dt = _pillow_exif_date(path)
    if not dt and kind_of(path) in ("image", "raw"):
        dt = _pyexiv2_date(path)
    return dt or _date_from_name(path.name) or datetime.fromtimestamp(path.stat().st_mtime)


def video_date(path: Path) -> datetime:
    """Container creation time, else a date in the file name, else the modification time."""
    path = Path(path)
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format_tags=creation_time",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        text = result.stdout.strip()
        if text:
            return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass
    return _date_from_name(path.name) or datetime.fromtimestamp(path.stat().st_mtime)


def media_date(path: Path) -> datetime:
    return video_date(path) if kind_of(Path(path)) == "video" else photo_date(path)
