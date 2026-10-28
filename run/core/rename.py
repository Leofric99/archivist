"""Rename photos and videos to the standard YYYYMMDD_HHMMSS[_suffix][_n].ext format."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .common import Cancelled, Context, Item, Operation, OperationError, Param, Plan, Reporter, kind_of
from .dates import media_date, validate_date_string


def clean_suffix(text: str) -> str:
    """Normalise a user supplied suffix into a safe lowercase file name fragment."""
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text or "")
    return "_".join(text.split()).lower()


def _file_id(path: Path):
    try:
        st = os.stat(path)
        return (st.st_dev, st.st_ino)
    except OSError:
        return None


def _finalize(op: str, renames: list, skipped_note: list) -> Plan:
    """Turn (source, target) pairs into a plan, flagging collisions with other files."""
    plan = Plan(op=op, warnings=list(skipped_note))
    source_ids = {_file_id(src) for src, _ in renames}
    seen_targets = set()
    payload = []
    for src, dst in sorted(renames, key=lambda pair: str(pair[0])):
        item = Item(source=str(src), target=str(dst), action="rename")
        key = str(dst).lower()
        if src.name == dst.name:
            item.status, item.note = "skip", "already named correctly"
        elif key in seen_targets:
            item.status, item.note = "error", "another file in this batch would get the same name"
        elif dst.exists() and _file_id(dst) not in source_ids:
            item.status, item.note = "error", "a different file with this name already exists"
        else:
            payload.append((src, dst))
        seen_targets.add(key)
        plan.items.append(item)
    plan.payload = payload
    n_err = sum(1 for i in plan.items if i.status == "error")
    if n_err:
        plan.warnings.append(f"{n_err} file(s) cannot be renamed because of name collisions and will be skipped.")
    plan.summary = f"{len(payload)} of {len(plan.items)} file(s) will be renamed."
    return plan


def _group_and_name(entries: list) -> list:
    """entries: [(path, base)] -> [(path, new_path)], numbering files that share a base name."""
    groups = {}
    for path, base in entries:
        groups.setdefault(base, []).append(path)
    out = []
    for base, paths in groups.items():
        paths = sorted(paths)
        for idx, path in enumerate(paths, start=1):
            name = f"{base}{f'_{idx}' if len(paths) > 1 else ''}{path.suffix.lower()}"
            out.append((path, path.with_name(name)))
    return out


def _filter_kinds(files: list, allowed: set) -> tuple:
    kept = [f for f in files if kind_of(f) in allowed]
    note = []
    if len(kept) != len(files):
        note.append(f"{len(files) - len(kept)} selected file(s) were ignored because their type is not included.")
    return kept, note


def apply_renames(ctx: Context, plan: Plan, rep: Reporter) -> None:
    """Rename via temporary names so swaps and chains between files in the batch are safe."""
    moves = plan.payload
    rep.start(len(moves) * 2)
    staged = []
    try:
        for src, dst in moves:
            rep.begin_item(src.name)
            tmp = src.with_name(f".archivist-{uuid.uuid4().hex[:8]}-{src.name}")
            try:
                src.rename(tmp)
                staged.append((src, tmp, dst))
            except OSError as exc:
                rep.failed(f"Could not rename {src.name}: {exc}")
            rep.end_item()
    except Cancelled:
        for src, tmp, _ in staged:
            tmp.rename(src)
        raise
    for src, tmp, dst in staged:
        rep.label = src.name
        try:
            tmp.rename(dst)
            rep.ok(f"{src.name} -> {dst.name}")
        except OSError as exc:
            try:
                tmp.rename(src)
            except OSError:
                pass
            rep.failed(f"Could not rename {src.name}: {exc}")
        rep.end_item()


# ---- Digital photographs ----


def plan_digital(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    allowed = {"image"}
    if params.get("include_raw"):
        allowed.add("raw")
    if params.get("include_video"):
        allowed.add("video")
    files, notes = _filter_kinds(files, allowed)
    suffix = clean_suffix(params.get("suffix", ""))
    custom_date = (params.get("custom_date") or "").strip()
    if custom_date:
        try:
            custom_date = validate_date_string(custom_date, lengths=(8,))
        except ValueError as exc:
            raise OperationError(str(exc))
    entries = []
    for path in files:
        dt = media_date(path)
        base = f"{custom_date}_{dt.strftime('%H%M%S')}" if custom_date else dt.strftime("%Y%m%d_%H%M%S")
        entries.append((path, base + (f"_{suffix}" if suffix else "")))
    return _finalize("rename_digital", _group_and_name(entries), notes)


# ---- Film scans ----


def plan_film(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    allowed = {"image", "raw"} if params.get("include_raw") else {"image"}
    files, notes = _filter_kinds(files, allowed)
    try:
        date = validate_date_string(params.get("date", ""))
    except ValueError as exc:
        raise OperationError(str(exc))
    suffix = clean_suffix(params.get("suffix", ""))
    base = date + (f"_{suffix}" if suffix else "")
    files = sorted(files)
    renames = []
    for idx, path in enumerate(files, start=1):
        name = f"{base}_{idx}{path.suffix.lower()}" if len(files) > 1 else f"{base}{path.suffix.lower()}"
        renames.append((path, path.with_name(name)))
    return _finalize("rename_film", renames, notes)


# ---- Videos ----


def plan_videos(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    files, notes = _filter_kinds(files, {"video"})
    suffix = clean_suffix(params.get("suffix", ""))
    custom_date = (params.get("custom_date") or "").strip()
    if custom_date:
        try:
            custom_date = validate_date_string(custom_date, lengths=(8,))
        except ValueError as exc:
            raise OperationError(str(exc))
    entries = []
    for path in files:
        dt = media_date(path)
        base = f"{custom_date}_{dt.strftime('%H%M%S')}" if custom_date else dt.strftime("%Y%m%d_%H%M%S")
        entries.append((path, base + (f"_{suffix}" if suffix else "")))
    return _finalize("rename_videos", _group_and_name(entries), notes)


INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_NAME_BYTES = 255


def rename_file(src: Path, new_name: str) -> Path:
    """Rename one file, keeping its extension. Never overwrites another file; returns the new path.

    `new_name` is the name without the extension; if the user also typed the current extension it is
    ignored rather than doubled.
    """
    stem = (new_name or "").strip()
    if stem.lower().endswith(src.suffix.lower()) and src.suffix:
        stem = stem[: -len(src.suffix)].strip()
    if not stem or stem in (".", ".."):
        raise OperationError("Enter a file name.")
    if INVALID_NAME_CHARS.search(stem):
        raise OperationError('A file name cannot contain / \\ : * ? " < > | or control characters.')
    if stem.startswith("."):
        raise OperationError("A file name cannot start with a dot (the file would become hidden).")
    if stem.endswith("."):
        raise OperationError("A file name cannot end with a dot.")
    target = src.with_name(stem + src.suffix)
    if len(target.name.encode("utf-8")) > MAX_NAME_BYTES:
        raise OperationError("That file name is too long.")
    if target == src:
        return src
    if target.exists() and not target.samefile(src):  # samefile: allows case-only renames on case-insensitive disks
        raise OperationError(f"A file named '{target.name}' already exists in this folder.")
    try:
        src.rename(target)
    except OSError as exc:
        raise OperationError(f"Could not rename: {exc.strerror or exc}") from None
    return target


SUFFIX_PARAM = Param(
    "suffix", "Custom suffix", "text",
    help="Optional event name appended to the file name. Use words without numbers, e.g. 'Italy' or "
         "'Trip to Yorkshire', otherwise Restructure Folders will not group them correctly.",
)

OPERATIONS = [
    Operation(
        id="rename_digital", label="Rename digital photographs", group="photos",
        description="Rename to YYYYMMDD_HHMMSS[_suffix][_n].ext using the capture date from metadata, "
                    "the file name, or the file modification time.",
        params=[
            SUFFIX_PARAM,
            Param("custom_date", "Custom date (replaces the date part)", "date",
                  help="YYYYMMDD. The time of day still comes from the file."),
            Param("include_raw", "Include RAW files", "bool", default=False),
            Param("include_video", "Include videos", "bool", default=False),
        ],
        plan=plan_digital, apply=apply_renames, accepts=("image", "raw", "video"),
    ),
    Operation(
        id="rename_film", label="Rename film scans", group="photos",
        description="Rename scans to YYYYMMDD[_suffix]_n.ext using one date you provide for all files.",
        params=[
            Param("date", "Date for all files", "date", required=True, help="YYYYMMDD, YYYYMM or YYYY."),
            SUFFIX_PARAM,
            Param("include_raw", "Include RAW files", "bool", default=False),
        ],
        plan=plan_film, apply=apply_renames, accepts=("image", "raw"),
    ),
    Operation(
        id="rename_videos", label="Rename videos", group="videos",
        description="Rename to YYYYMMDD_HHMMSS[_suffix][_n].ext using the video creation date, the file "
                    "name, or the file modification time.",
        params=[
            SUFFIX_PARAM,
            Param("custom_date", "Custom date (replaces the date part)", "date", help="YYYYMMDD."),
        ],
        plan=plan_videos, apply=apply_renames, accepts=("video",),
    ),
]
