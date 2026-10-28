"""Discover the fonts available on this machine (plus any in the repo's fonts/ folder) for burn-in text."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import ImageFont

from ..config import CAPTION_FONT_DEFAULTS
from .common import OperationError

FONT_DIR = Path(__file__).resolve().parents[2] / "fonts"
FONT_EXTS = {".ttf", ".otf", ".ttc"}
REGULAR_STYLES = {"regular", "roman", "book", "normal", "medium"}
EXCLUDED_WORDS = ("emoji", "symbol", "dingbat", "webdings", "wingdings", "lastresort", "ornament", "braille",
                  "icons", "music", "math")
MAX_TTC_FACES = 24


def _system_dirs() -> list:
    home = Path.home()
    dirs = [
        FONT_DIR,
        Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
        home / "Library" / "Fonts",
        Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".fonts", home / ".local/share/fonts",
    ]
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    return dirs


def _can_draw_latin(font: ImageFont.FreeTypeFont) -> bool:
    """True if the font really has Latin letters (not blank glyphs or its missing-glyph box)."""
    try:
        missing = font.getmask("\U0010FFFF")
        for ch in "Aag":
            glyph = font.getmask(ch)
            if glyph.getbbox() is None or (glyph.size == missing.size and bytes(glyph) == bytes(missing)):
                return False
        return True
    except Exception:
        return False


def _faces(path: Path):
    """Yield (family, style, face index) for each face in a font file."""
    for index in range(MAX_TTC_FACES if path.suffix.lower() == ".ttc" else 1):
        try:
            font = ImageFont.truetype(str(path), 12, index=index)
            family, style = font.getname()
        except Exception:
            return
        if family and _can_draw_latin(font):
            yield family, (style or "").lower(), index


@lru_cache(maxsize=1)
def available_fonts() -> dict:
    """Map family name -> (path, face index), regular weights only; repo fonts win over system fonts."""
    found: dict = {}
    seen_paths = set()
    for folder in _system_dirs():
        if not folder.is_dir():
            continue
        for dirpath, _dirs, files in os.walk(folder):
            for name in sorted(files):
                path = Path(dirpath) / name
                if path.suffix.lower() not in FONT_EXTS or name.startswith(".") or path in seen_paths:
                    continue
                seen_paths.add(path)
                for family, style, index in _faces(path):
                    lowered = family.lower()
                    if family.startswith(".") or any(w in lowered for w in EXCLUDED_WORDS):
                        continue
                    if style in REGULAR_STYLES and family not in found:
                        found[family] = (path, index)
    return dict(sorted(found.items(), key=lambda kv: kv[0].lower()))


def font_names() -> list:
    return list(available_fonts())


def default_font_name() -> Optional[str]:
    fonts = available_fonts()
    for name in CAPTION_FONT_DEFAULTS:
        if name in fonts:
            return name
    return next(iter(fonts), None)


def load_font(name: Optional[str], size: int) -> ImageFont.ImageFont:
    """Load a font by family name (None = default). Unknown names raise OperationError."""
    fonts = available_fonts()
    name = name or default_font_name()
    if name is not None:
        if name not in fonts:
            raise OperationError(f"Unknown font: {name}")
        path, index = fonts[name]
        try:
            return ImageFont.truetype(str(path), size, index=index)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
