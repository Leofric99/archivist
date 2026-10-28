"""Read, export, import and clone image metadata."""
from __future__ import annotations

import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import ExifTags, Image

from ..config import EXIF_TAG_MAP
from .common import (PYEXIV2_LOCK, Cancelled, Context, Item, Operation, OperationError, Param, Plan,
                     Reporter, kind_of, to_path)

EXIF_IFD = 0x8769
MAX_VALUE_LENGTH = 300


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= MAX_VALUE_LENGTH else text[:MAX_VALUE_LENGTH] + "…"


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ---- Reading (for the details panel) ----


def read_info(path: Path) -> dict:
    """Return {'sections': [{'title': str, 'rows': [[key, value], ...]}]} describing a file."""
    st = path.stat()
    sections = [{"title": "File", "rows": [
        ["Name", path.name], ["Size", f"{st.st_size:,} bytes"], ["Modified", _fmt_time(st.st_mtime)],
        ["Type", (kind_of(path) or "unknown")],
    ]}]
    kind = kind_of(path)
    if kind == "video":
        sections.extend(_video_sections(path))
        return sections_dict(sections)
    try:
        with Image.open(path) as img:
            sections.append({"title": "Image", "rows": [
                ["Dimensions", f"{img.width} × {img.height}"], ["Format", img.format or ""]]})
    except Exception:
        pass
    try:
        import pyexiv2
        with PYEXIV2_LOCK, pyexiv2.Image(str(path)) as meta:
            for title, data in (("EXIF", meta.read_exif()), ("IPTC", meta.read_iptc()), ("XMP", meta.read_xmp())):
                rows = [[k, _short(v)] for k, v in data.items() if not k.startswith("Exif.Thumbnail")]
                if rows:
                    sections.append({"title": title, "rows": rows})
    except Exception:
        pass
    return sections_dict(sections)


def sections_dict(sections: list) -> dict:
    return {"sections": sections}


def _video_sections(path: Path) -> list:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60).stdout
        data = json.loads(out or "{}")
    except Exception:
        return []
    fmt = data.get("format", {})
    rows = [["Container", fmt.get("format_long_name", "")], ["Duration", f"{float(fmt.get('duration') or 0):.1f} s"]]
    tags = fmt.get("tags") or {}
    if tags.get("creation_time"):
        rows.append(["Created", tags["creation_time"]])
    sections = [{"title": "Video", "rows": rows}]
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            sections.append({"title": "Video stream", "rows": [
                ["Codec", stream.get("codec_name", "")],
                ["Dimensions", f"{stream.get('width')} × {stream.get('height')}"],
                ["Frame rate", stream.get("avg_frame_rate", "")]]})
        elif stream.get("codec_type") == "audio":
            sections.append({"title": "Audio stream", "rows": [
                ["Codec", stream.get("codec_name", "")], ["Channels", str(stream.get("channels", ""))]]})
    return sections


# ---- Export ----


def collect_metadata(path: Path, rel: str) -> dict:
    with Image.open(path) as img:
        exif = img.getexif()
        merged = dict(exif)
        merged.update(exif.get_ifd(EXIF_IFD))
    st = path.stat()
    return {
        "File Name": path.name,
        "Relative Path": rel,
        "File Size": st.st_size,
        "Date Created": _fmt_time(st.st_ctime),
        "Date Modified": _fmt_time(st.st_mtime),
        "EXIF Data": {str(ExifTags.TAGS.get(k, k)): str(v) for k, v in merged.items()},
    }


def write_json(path: Path, data: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, data: list) -> None:
    fields = list(data[0].keys()) if data else ["File Name"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in data:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v
                             for k, v in record.items()})


def plan_export(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    fmt = params.get("format") or "both"
    if fmt not in ("csv", "json", "both"):
        raise OperationError("Format must be csv, json or both.")
    out_dir = to_path(params.get("output_dir", ""))
    targets = [out_dir / f"metadata.{ext}" for ext in (("json", "csv") if fmt == "both" else (fmt,))]
    plan = Plan(op="export_metadata")
    for f in sorted(files):
        if kind_of(f) == "image":
            plan.items.append(Item(str(f), None, "export"))
        else:
            plan.items.append(Item(str(f), None, "export", "skip", "only standard image formats are exported"))
    for t in targets:
        if t.exists():
            plan.warnings.append(f"{t} already exists and will be overwritten.")
    plan.payload = (out_dir, targets, [Path(i.source) for i in plan.items if i.status == "ok"])
    plan.summary = f"Metadata for {plan.actionable} image(s) will be written to " + ", ".join(t.name for t in targets) \
        + f" in {out_dir}."
    return plan


def apply_export(ctx: Context, plan: Plan, rep: Reporter) -> None:
    out_dir, targets, files = plan.payload
    rep.start(len(files))
    records = []
    for path in files:
        rep.begin_item(path.name)
        try:
            records.append(collect_metadata(path, ctx.rel(path)))
            rep.ok(f"Read {path.name}")
        except Cancelled:
            raise
        except Exception as exc:
            rep.failed(f"{path.name}: {exc}")
        rep.end_item()
    out_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        (write_json if target.suffix == ".json" else write_csv)(target, records)
        rep.log(f"Wrote {target}", "ok")


# ---- Import ----


def load_metadata_file(path: Path) -> list:
    if path.suffix.lower() not in (".csv", ".json"):
        raise OperationError("The metadata file must be a .csv or .json file.")
    if not path.is_file():
        raise OperationError(f"File not found: {path}")
    if path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise OperationError("Expected a JSON list of metadata records.")
        return [r for r in data if isinstance(r, dict)]
    records = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for key in ("EXIF Data", "IPTC Data", "XMP Data"):
                if isinstance(row.get(key), str):
                    try:
                        row[key] = json.loads(row[key])
                    except ValueError:
                        row[key] = {}
            records.append(row)
    return records


def plan_import(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    meta_file = to_path(params.get("metadata_file", ""))
    records = load_metadata_file(meta_file)
    by_rel = {r["Relative Path"]: r for r in records if r.get("Relative Path")}
    by_name = {}
    for r in records:
        if r.get("File Name"):
            by_name.setdefault(r["File Name"], []).append(r)
    plan = Plan(op="import_metadata")
    payload = []
    for f in sorted(files):
        rec = by_rel.get(ctx.rel(f))
        if rec is None:
            candidates = by_name.get(f.name, [])
            if len(candidates) > 1:
                plan.items.append(Item(str(f), None, "import", "skip", "several records share this file name"))
                continue
            rec = candidates[0] if candidates else None
        if rec is None:
            plan.items.append(Item(str(f), None, "import", "skip", "no matching record"))
            continue
        exif = {k: v for k, v in (rec.get("EXIF Data") or {}).items() if k in EXIF_TAG_MAP}
        unknown = len(rec.get("EXIF Data") or {}) - len(exif)
        iptc, xmp = rec.get("IPTC Data") or {}, rec.get("XMP Data") or {}
        note = f"{len(exif)} EXIF, {len(iptc)} IPTC, {len(xmp)} XMP tag(s)" + (f"; {unknown} unsupported EXIF tag(s) ignored" if unknown else "")
        plan.items.append(Item(str(f), None, "import", "ok", note))
        payload.append((f, exif, iptc, xmp))
    plan.payload = payload
    plan.summary = f"{len(payload)} of {len(plan.items)} file(s) match records in {meta_file.name}."
    if payload:
        plan.warnings.append("Metadata is written into the image files themselves.")
    return plan


def apply_import(ctx: Context, plan: Plan, rep: Reporter) -> None:
    import pyexiv2
    rep.start(len(plan.payload))
    for path, exif, iptc, xmp in plan.payload:
        rep.begin_item(path.name)
        try:
            with PYEXIV2_LOCK, pyexiv2.Image(str(path)) as meta:
                for tag, value in exif.items():
                    try:
                        meta.modify_exif({EXIF_TAG_MAP[tag]: value})
                    except Exception as exc:
                        rep.log(f"{path.name}: could not set EXIF {tag}: {exc}", "warn")
                for tag, value in iptc.items():
                    try:
                        meta.modify_iptc({tag: value})
                    except Exception as exc:
                        rep.log(f"{path.name}: could not set IPTC {tag}: {exc}", "warn")
                for tag, value in xmp.items():
                    try:
                        meta.modify_xmp({tag: value})
                    except Exception as exc:
                        rep.log(f"{path.name}: could not set XMP {tag}: {exc}", "warn")
            rep.ok(f"Updated {path.name}")
        except Cancelled:
            raise
        except Exception as exc:
            rep.failed(f"{path.name}: {exc}")
        rep.end_item()


# ---- Clone ----


def _resolve_source(ctx: Context, value: str) -> Path:
    value = (value or "").strip()
    if not value:
        raise OperationError("Choose a source image.")
    if Path(value.strip("'\"")).expanduser().is_absolute():
        return to_path(value)
    return ctx.resolve_inside(value)


def plan_clone(ctx: Context, files: list, params: dict, answers: dict) -> Plan:
    source = _resolve_source(ctx, params.get("source", ""))
    if not source.is_file():
        raise OperationError(f"Source file not found: {source}")
    plan = Plan(op="clone_metadata")
    targets = []
    for f in sorted(files):
        if f.resolve() == source:
            plan.items.append(Item(str(f), None, "clone", "skip", "this is the source image"))
        elif kind_of(f) in ("image", "raw"):
            plan.items.append(Item(str(f), None, "clone", "ok"))
            targets.append(f)
        else:
            plan.items.append(Item(str(f), None, "clone", "skip", "not an image"))
    plan.payload = (source, targets)
    plan.summary = f"Metadata from {source.name} will be copied to {len(targets)} file(s)."
    if targets:
        plan.warnings.append("Existing EXIF/IPTC/XMP data and file timestamps of the targets will be overwritten.")
    return plan


def apply_clone(ctx: Context, plan: Plan, rep: Reporter) -> None:
    import pyexiv2
    source, targets = plan.payload
    with PYEXIV2_LOCK, pyexiv2.Image(str(source)) as src:
        exif, iptc, xmp = src.read_exif(), src.read_iptc(), src.read_xmp()
    st = source.stat()
    rep.start(len(targets))
    for target in targets:
        rep.begin_item(target.name)
        try:
            with PYEXIV2_LOCK, pyexiv2.Image(str(target)) as dst:
                dst.modify_exif(exif)
                dst.modify_iptc(iptc)
                dst.modify_xmp(xmp)
            try:
                os.utime(target, (st.st_atime, st.st_mtime))
            except OSError as exc:
                rep.log(f"Could not copy timestamps to {target.name}: {exc}", "warn")
            rep.ok(f"Cloned metadata to {target.name}")
        except Cancelled:
            raise
        except Exception as exc:
            rep.failed(f"{target.name}: {exc}")
        rep.end_item()


OPERATIONS = [
    Operation(
        id="export_metadata", label="Export metadata to CSV / JSON", group="metadata",
        description="Writes the EXIF data of the selected images to metadata.csv and/or metadata.json.",
        params=[
            Param("format", "Format", "choice", default="both",
                  choices=[["both", "CSV and JSON"], ["csv", "CSV"], ["json", "JSON"]]),
            Param("output_dir", "Output folder", "path", required=True,
                  help="Created if missing. Existing metadata files in it are overwritten."),
        ],
        plan=plan_export, apply=apply_export, accepts=("image", "raw"),
    ),
    Operation(
        id="import_metadata", label="Import metadata from CSV / JSON", group="metadata",
        description="Writes metadata from a previously exported file into the matching selected images.",
        params=[Param("metadata_file", "Metadata file", "path", required=True,
                      help="Full path of a .csv or .json file on this computer.")],
        plan=plan_import, apply=apply_import, accepts=("image", "raw"), destructive=True,
    ),
    Operation(
        id="clone_metadata", label="Clone metadata from another image", group="metadata",
        description="Copies EXIF, IPTC, XMP and timestamps from a source image onto the selected images "
                    "(useful when the targets lost their metadata).",
        params=[Param("source", "Source image", "file", required=True,
                      help="Pick a file from the opened folder or type a full path.")],
        plan=plan_clone, apply=apply_clone, accepts=("image", "raw"), destructive=True,
    ),
]
