"""Shared types and helpers used by every Archivist operation."""
from __future__ import annotations

import os
import platform
import re
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from PIL import Image

from ..config import IMAGE_EXTENSIONS, RAW_EXTENSIONS, VIDEO_EXTENSIONS

# Large scans are expected; don't treat them as decompression bombs.
Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

IMAGE_EXTS = frozenset(e.lower() for e in IMAGE_EXTENSIONS)
RAW_EXTS = frozenset(e.lower() for e in RAW_EXTENSIONS)
VIDEO_EXTS = frozenset(e.lower() for e in VIDEO_EXTENSIONS)

# Extensions of formats that can be re-encoded with a burned-in overlay.
BURNIN_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"})

# pyexiv2 is not safe to call from several threads at once.
PYEXIV2_LOCK = threading.RLock()

IGNORABLE_FILES = {".ds_store", "thumbs.db", "desktop.ini"}


class OperationError(Exception):
    """A user-facing error (bad input, unsafe request, ...)."""


class Cancelled(Exception):
    """Raised inside a running operation when the user cancels it."""


def kind_of(path: Path) -> Optional[str]:
    """Return 'image', 'raw', 'video' or None for a path based on its extension."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in RAW_EXTS:
        return "raw"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def clean_user_path(raw: str) -> str:
    """Strip whitespace/quotes and translate Windows paths when running under WSL."""
    text = (raw or "").strip().strip("'\"").strip()
    if platform.system() == "Linux" and ":" in text and "\\" in text:
        m = re.match(r"^([A-Za-z]):\\", text)
        if m:
            text = f"/mnt/{m.group(1).lower()}/" + text[3:].replace("\\", "/")
    return text


def to_path(raw: str) -> Path:
    text = clean_user_path(raw)
    if not text:
        raise OperationError("A path is required.")
    return Path(text).expanduser().resolve()


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def iter_media(root: Path, subdirs: bool = True, kinds: Optional[set] = None) -> Iterator[Path]:
    """Yield supported media files under root, skipping hidden files and folders."""
    root = Path(root)
    if subdirs:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                p = Path(dirpath) / name
                k = kind_of(p)
                if k and (kinds is None or k in kinds):
                    yield p
    else:
        for p in sorted(root.iterdir()):
            if p.name.startswith(".") or not p.is_file():
                continue
            k = kind_of(p)
            if k and (kinds is None or k in kinds):
                yield p


@dataclass
class Context:
    """Per-session state: the folder currently opened by the user."""
    root: Path

    def rel(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def resolve_inside(self, rel: str) -> Path:
        """Resolve a root-relative path, refusing anything that escapes the root."""
        if not isinstance(rel, str) or not rel or "\x00" in rel:
            raise OperationError("Invalid path.")
        candidate = (self.root / rel).resolve()
        if not is_within(candidate, self.root):
            raise OperationError("Path is outside the opened folder.")
        return candidate


@dataclass
class Param:
    """Declarative description of an operation input; drives both web forms and CLI prompts."""
    name: str
    label: str
    kind: str = "text"  # text | bool | choice | date | path | file
    default: Any = None
    choices: Optional[list] = None  # list of [value, label]
    required: bool = False
    help: str = ""
    show_if: Optional[dict] = None  # {"param_name": value}
    choices_fn: Optional[Callable] = None  # computed on demand (e.g. installed fonts)
    default_fn: Optional[Callable] = None

    def get_choices(self) -> Optional[list]:
        return self.choices_fn() if self.choices_fn else self.choices

    def get_default(self) -> Any:
        return self.default_fn() if self.default_fn else self.default

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "kind": self.kind,
            "default": self.get_default(), "choices": self.get_choices(),
            "required": self.required, "help": self.help, "show_if": self.show_if,
        }


@dataclass
class Item:
    source: str
    target: Optional[str] = None
    action: str = ""
    status: str = "ok"  # ok | skip | error
    note: str = ""

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target, "action": self.action,
                "status": self.status, "note": self.note}


@dataclass
class Plan:
    """What an operation would do, computed without touching any files."""
    op: str
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    summary: str = ""
    confirmation: Optional[dict] = None  # {"message": str, "expected": str}
    payload: Any = None  # operation-private data used by apply(); never serialised
    options: dict = field(default_factory=dict)  # validated settings apply() needs, e.g. the font

    @property
    def actionable(self) -> int:
        return sum(1 for i in self.items if i.status == "ok")

    @property
    def ready(self) -> bool:
        return not self.errors and not self.questions and self.actionable > 0

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "items": [i.to_dict() for i in self.items],
            "warnings": self.warnings,
            "errors": self.errors,
            "questions": self.questions,
            "summary": self.summary,
            "confirmation": self.confirmation,
            "actionable": self.actionable,
            "ready": self.ready,
        }


class Reporter:
    """Receives progress and log messages from a running operation."""

    def __init__(self, on_log: Optional[Callable] = None, on_progress: Optional[Callable] = None,
                 cancel_event: Optional[threading.Event] = None):
        self._on_log = on_log
        self._on_progress = on_progress
        self._cancel = cancel_event or threading.Event()
        self.total = 0
        self.done = 0
        self.label = ""
        self.fraction = 0.0
        self.n_ok = 0
        self.n_skipped = 0
        self.n_failed = 0

    def check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def log(self, message: str, level: str = "info") -> None:
        if self._on_log:
            self._on_log(message, level)

    def ok(self, message: str) -> None:
        self.n_ok += 1
        self.log(message, "ok")

    def skipped(self, message: str) -> None:
        self.n_skipped += 1
        self.log(message, "warn")

    def failed(self, message: str) -> None:
        self.n_failed += 1
        self.log(message, "error")

    def start(self, total: int) -> None:
        self.total, self.done, self.fraction = total, 0, 0.0
        self._emit()

    def begin_item(self, label: str) -> None:
        self.check()
        self.label, self.fraction = label, 0.0
        self._emit()

    def item_progress(self, fraction: float) -> None:
        self.fraction = max(0.0, min(1.0, fraction))
        self._emit()

    def end_item(self) -> None:
        self.done += 1
        self.fraction = 0.0
        self._emit()

    def _emit(self) -> None:
        if self._on_progress:
            self._on_progress({"total": self.total, "done": self.done,
                               "label": self.label, "fraction": self.fraction})


@dataclass
class Operation:
    id: str
    label: str
    group: str  # photos | videos | metadata | folder
    description: str
    params: list
    plan: Callable  # (ctx, files, params, answers) -> Plan
    apply: Callable  # (ctx, plan, reporter) -> None
    scope: str = "files"  # files: acts on selected files; folder: acts on the whole opened folder
    accepts: tuple = ("image", "raw", "video")
    captions: Optional[str] = None  # None | "optional" | "required": per-file text editor
    preview: Optional[Callable] = None  # (ctx, path, params, caption) -> PIL image
    destructive: bool = False
    editor: Optional[str] = None  # name of a custom web editor, e.g. 'crop'

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "group": self.group,
            "description": self.description, "scope": self.scope,
            "accepts": list(self.accepts), "captions": self.captions,
            "previewable": self.preview is not None, "editor": self.editor,
            "destructive": self.destructive,
            "params": [p.to_dict() for p in self.params],
        }
