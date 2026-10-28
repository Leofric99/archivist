"""Reorganise standard-named photos and videos into decade / year / event-or-month folders."""
from __future__ import annotations

import concurrent.futures
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..config import EVENT_FOLDER_THRESHOLD
from .common import (IGNORABLE_FILES, IMAGE_EXTS, RAW_EXTS, VIDEO_EXTS, Cancelled, Context, Item, Operation,
                     Param, Plan, Reporter, is_within, to_path)

ALL_EXTS = IMAGE_EXTS | RAW_EXTS | VIDEO_EXTS | {".psd"}

PATTERN_FULL = re.compile(r"^(\d{8})_(\d{6})((?:_[a-z0-9]+)*)(?:_([0-9]+))?\.[a-z0-9]+$", re.IGNORECASE)
PATTERN_SHORT = re.compile(r"^(\d{6})_(\d{6})((?:_[a-z0-9]+)*)(?:_([0-9]+))?\.[a-z0-9]+$", re.IGNORECASE)
MAX_LISTED_PROBLEMS = 200


def parse_name(name: str):
    """Return (date, event suffix or None) for a standard file name, or None if it does not conform."""
    m = PATTERN_FULL.match(name) or PATTERN_SHORT.match(name)
    if not m:
        return None
    date_str = m.group(1)
    cleaned = re.sub(r"_\d+$", "", m.group(3))
    suffix = None
    if cleaned:
        parts = cleaned.strip("_").split("_")
        if len(parts) >= 2 and parts[-1].isdigit() and not parts[-2].isdigit():
            suffix = f"{parts[-2].capitalize()} {parts[-1]}"
        elif not (len(parts) == 1 and parts[-1].isdigit()):
            suffix = "_".join(parts).capitalize()
    try:
        if len(date_str) == 8:
            date = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        else:
            date = datetime(2000 + int(date_str[:2]), int(date_str[2:4]), 1)
    except ValueError:
        return None
    return date, suffix


def _month_folder(date: datetime) -> str:
    return f"{date.month}. {date.strftime('%B')}"


def _scan(src: Path) -> list:
    found = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if not name.startswith(".") and p.suffix.lower() in ALL_EXTS:
                found.append(p)
    return found


def _check_destination(src: Path, dest: Path) -> list:
    errors = []
    if dest == Path(dest.anchor) or dest == Path.home().resolve():
        errors.append("That destination is a top-level or home folder and cannot be used.")
    if dest != src and is_within(dest, src):
        errors.append("The destination cannot be inside the folder being restructured.")
    if dest != src and is_within(src, dest):
        errors.append("The destination cannot contain the folder being restructured; its contents would be deleted.")
    return errors


def plan_restructure(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    src = ctx.root.resolve()
    dest = to_path(params.get("dest_dir", ""))
    same_dir = dest == src
    plan = Plan(op="restructure")
    plan.errors.extend(_check_destination(src, dest))
    if plan.errors:
        return plan

    found = _scan(src)
    infos, bad = [], []
    for path in found:
        parsed = parse_name(path.name)
        if parsed:
            infos.append({"path": path, "date": parsed[0], "suffix": parsed[1]})
        else:
            bad.append(path)
    if not found:
        plan.errors.append("No supported files were found in the opened folder.")
        return plan
    if bad:
        for path in bad[:MAX_LISTED_PROBLEMS]:
            plan.items.append(Item(ctx.rel(path), None, "restructure", "error", "name is not in the standard format"))
        plan.errors.append(
            f"{len(bad)} file(s) do not follow the standard naming scheme (YYYYMMDD_HHMMSS[_event][_n].ext). "
            "Rename them first, then restructure.")
        return plan

    by_suffix, by_month = defaultdict(list), defaultdict(list)
    for info in infos:
        if info["suffix"]:
            by_suffix[info["suffix"]].append(info)
        else:
            by_month[(info["date"].year, info["date"].month)].append(info)
    suffix_counts = {k: len(v) for k, v in by_suffix.items()}

    assignments = []  # (info, target folder)
    for suffix, group in by_suffix.items():
        group = sorted(group, key=lambda i: i["date"])
        folders, current = [], [group[0]]
        for prev, curr in zip(group, group[1:]):
            if curr["date"].year - prev["date"].year > 1:
                qid = f"{suffix}::{ctx.rel(prev['path'])}::{ctx.rel(curr['path'])}"
                if qid not in answers:
                    plan.questions.append({
                        "id": qid,
                        "prompt": f"Files in the event '{suffix}' are more than a year apart. Group them together?",
                        "detail": f"{prev['path'].name} ({prev['date'].date()}) and {curr['path'].name} "
                                  f"({curr['date'].date()})",
                    })
                if answers.get(qid) is True:
                    current.append(curr)
                else:
                    folders.append(current)
                    current = [curr]
            else:
                current.append(curr)
        folders.append(current)
        for folder_files in folders:
            earliest = min(folder_files, key=lambda i: i["date"])
            year = earliest["date"].year
            base = dest / f"{(year // 10) * 10}s" / str(year)
            if suffix_counts.get(earliest["suffix"], 0) >= EVENT_FOLDER_THRESHOLD:
                target = base / earliest["suffix"]
            else:
                target = base / _month_folder(earliest["date"])
            assignments.extend((info, target) for info in folder_files)
    for (year, month), group in by_month.items():
        target = dest / f"{(year // 10) * 10}s" / str(year) / _month_folder(datetime(year, month, 1))
        assignments.extend((info, target) for info in group)

    action = "move" if same_dir else "copy"
    seen, payload, folders_used = set(), [], set()
    for info, folder in sorted(assignments, key=lambda a: str(a[0]["path"])):
        path, target = info["path"], folder / info["path"].name
        item = Item(ctx.rel(path), str(target), action)
        if path == target:
            item.status, item.note = "skip", "already in the right place"
        elif str(target).lower() in seen:
            item.status, item.note = "error", "another file already goes to this exact path"
        elif same_dir and target.exists():
            item.status, item.note = "error", "a different file already exists there"
        else:
            payload.append((path, target))
            folders_used.add(folder)
        seen.add(str(target).lower())
        plan.items.append(item)

    if any(i.status == "error" for i in plan.items):
        plan.warnings.append("Files marked as errors will be skipped.")
    plan.payload = {"src": src, "dest": dest, "same_dir": same_dir, "moves": payload}
    plan.summary = (f"{len(payload)} file(s) will be {'moved' if same_dir else 'copied'} into "
                    f"{len(folders_used)} folder(s) under {dest}.")
    existing = [p for p in dest.iterdir()] if (not same_dir and dest.is_dir()) else []
    if same_dir:
        plan.warnings.append("The files are moved inside the opened folder. This cannot be undone.")
        plan.confirmation = {"message": "Type the folder name to confirm moving files in place:", "expected": dest.name}
    elif existing:
        plan.warnings.append(f"EVERYTHING currently inside {dest} ({len(existing)} item(s)) will be deleted first.")
        plan.confirmation = {"message": "Type the destination folder name to confirm deleting its contents:",
                             "expected": dest.name}
    return plan


def _clear_directory(dest: Path) -> None:
    for item in dest.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def _prune_empty_dirs(root: Path) -> list:
    removed = []
    for dirpath, _dirs, _files in os.walk(root, topdown=False):
        folder = Path(dirpath)
        if folder == root:
            continue
        entries = os.listdir(folder)
        if all(e.lower() in IGNORABLE_FILES for e in entries):
            shutil.rmtree(folder)
            removed.append(folder)
    return removed


def apply_restructure(ctx: Context, plan: Plan, rep: Reporter) -> None:
    data = plan.payload
    dest, same_dir, moves = data["dest"], data["same_dir"], data["moves"]
    rep.start(len(moves))
    if not same_dir:
        if dest.exists():
            rep.log(f"Clearing {dest} ...", "warn")
            _clear_directory(dest)
        else:
            dest.mkdir(parents=True)

    def transfer(src: Path, target: Path) -> str:
        rep.check()
        target.parent.mkdir(parents=True, exist_ok=True)
        if same_dir:
            os.rename(src, target)
        else:
            shutil.copy2(src, target)
        return f"{'Moved' if same_dir else 'Copied'} {src.name} -> {target.parent.relative_to(dest)}"

    workers = 1 if same_dir else 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(transfer, s, t): s for s, t in moves}
        try:
            for future in concurrent.futures.as_completed(futures):
                src = futures[future]
                try:
                    rep.ok(future.result())
                except Cancelled:
                    raise
                except Exception as exc:
                    rep.failed(f"{src.name}: {exc}")
                rep.label = src.name
                rep.end_item()
        except Cancelled:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    if same_dir:
        for folder in _prune_empty_dirs(dest):
            rep.log(f"Removed empty folder {ctx.rel(folder)}", "info")


OPERATIONS = [
    Operation(
        id="restructure", label="Restructure folders", group="folder", scope="folder", destructive=True,
        description="Sorts every photo and video in the opened folder (including sub-folders) into "
                    "decade / year / event-or-month folders based on its standard file name. "
                    "Rename files to the standard format first.",
        params=[Param(
            "dest_dir", "Destination folder", "path", required=True,
            help="Files are copied here and anything already in this folder is deleted. "
                 "Enter the opened folder itself to move files in place instead.")],
        plan=plan_restructure, apply=apply_restructure,
    ),
]
