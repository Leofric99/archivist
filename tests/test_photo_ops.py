import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from run.core import ops
from run.core.common import OperationError
from run.core.metadata import load_metadata_file
from tests.conftest import make_jpeg, names, run

BASIC = ops.get("burnin_basic")
CAPTION = ops.get("burnin_caption")
EXPORT = ops.get("export_metadata")
IMPORT = ops.get("import_metadata")


def test_burnin_needs_output_or_overwrite(root, ctx):
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        BASIC.plan(ctx, [a], {"overwrite": False, "output_dir": ""}, {})


def test_burnin_refuses_output_folder_equal_to_source(root, ctx):
    a = make_jpeg(root / "a.jpg")
    plan = BASIC.plan(ctx, [a], {"overwrite": False, "output_dir": str(root)}, {})
    assert plan.errors and not plan.ready


def test_burnin_writes_copy_and_keeps_original_and_exif(root, ctx, tmp_path):
    a = make_jpeg(root / "sub" / "a.jpg", datetime(2020, 5, 17, 1, 2, 3), size=(400, 300))
    original = a.read_bytes()
    out = tmp_path / "out"
    plan, rep = run(BASIC, ctx, [a], {"overwrite": False, "output_dir": str(out), "text": "Italy"})
    assert rep.n_ok == 1, rep
    result = out / "sub" / "a.jpg"
    assert result.exists() and a.read_bytes() == original
    with Image.open(result) as img:
        assert img.size == (400, 300)
        assert img.getexif().get_ifd(0x8769).get(36867) == "2020:05:17 01:02:03"
    assert not list(out.rglob(".*archivist-tmp*"))


def test_burnin_overwrite_replaces_original(root, ctx):
    a = make_jpeg(root / "a.jpg", size=(400, 300))
    original = a.read_bytes()
    plan, rep = run(BASIC, ctx, [a], {"overwrite": True, "custom_date": "20200101"})
    assert rep.n_ok == 1 and a.read_bytes() != original
    assert names(root) == ["a.jpg"]


def test_per_file_caption_overrides_common_text(root, ctx):
    a = make_jpeg(root / "a.jpg")
    b = make_jpeg(root / "b.jpg")
    plan = BASIC.plan(ctx, [a, b], {"overwrite": True, "text": "common", "captions": {"a.jpg": "mine"}}, {})
    texts = {p.name: t for p, _d, t, _c in plan.payload}
    assert texts == {"a.jpg": "mine", "b.jpg": "common"}


def test_caption_band_adds_height_and_blank_is_skipped(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg", size=(400, 300))
    b = make_jpeg(root / "b.jpg", size=(400, 300))
    params = {"overwrite": False, "output_dir": str(tmp_path / "out"), "captions": {"a.jpg": "A long caption " * 6}}
    plan, rep = run(CAPTION, ctx, [a, b], params)
    assert rep.n_ok == 1
    with Image.open(tmp_path / "out" / "a.jpg") as img:
        assert img.width == 400 and img.height > 300
    assert not (tmp_path / "out" / "b.jpg").exists()
    assert any(i.note == "no caption entered" for i in plan.items)


def test_unsupported_burnin_format_is_skipped(root, ctx):
    gif = root / "a.gif"
    Image.new("P", (8, 8)).save(gif)
    plan = BASIC.plan(ctx, [gif], {"overwrite": True}, {})
    assert plan.items[0].status == "skip" and not plan.ready


def test_export_roundtrips_through_csv_and_json(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3))
    out = tmp_path / "meta"
    plan, rep = run(EXPORT, ctx, [a], {"format": "both", "output_dir": str(out)})
    assert rep.n_ok == 1 and rep.n_failed == 0
    from_json = load_metadata_file(out / "metadata.json")
    from_csv = load_metadata_file(out / "metadata.csv")
    assert from_json[0]["EXIF Data"]["DateTimeOriginal"] == "2020:05:17 01:02:03"
    # The CSV used to store Python reprs that could not be read back.
    assert from_csv[0]["EXIF Data"] == from_json[0]["EXIF Data"]


def test_import_writes_exif_into_matching_file(root, ctx, tmp_path):
    source = make_jpeg(root / "source.jpg", datetime(2018, 8, 9, 10, 11, 12))
    target = make_jpeg(root / "target.jpg")
    meta_dir = tmp_path / "meta"
    run(EXPORT, ctx, [source], {"format": "json", "output_dir": str(meta_dir)})
    records = json.loads((meta_dir / "metadata.json").read_text())
    records[0]["File Name"], records[0]["Relative Path"] = "target.jpg", "target.jpg"
    (meta_dir / "metadata.json").write_text(json.dumps(records))
    plan, rep = run(IMPORT, ctx, [target], {"metadata_file": str(meta_dir / "metadata.json")})
    assert rep.n_ok == 1, rep
    with Image.open(target) as img:
        assert img.getexif().get_ifd(0x8769).get(36867) == "2018:08:09 10:11:12"


def test_import_skips_files_without_records(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg")
    meta = tmp_path / "m.json"
    meta.write_text("[]")
    plan = IMPORT.plan(ctx, [a], {"metadata_file": str(meta)}, {})
    assert plan.items[0].status == "skip" and not plan.ready


def test_clone_copies_exif_and_never_targets_source(root, ctx):
    src = make_jpeg(root / "src.jpg", datetime(2015, 3, 4, 5, 6, 7))
    dst = make_jpeg(root / "dst.jpg")
    clone = ops.get("clone_metadata")
    plan, rep = run(clone, ctx, [src, dst], {"source": "src.jpg"})
    assert rep.n_ok == 1, rep
    assert {Path(i.source).name: i.status for i in plan.items} == {"src.jpg": "skip", "dst.jpg": "ok"}
    with Image.open(dst) as img:
        assert img.getexif().get_ifd(0x8769).get(36867) == "2015:03:04 05:06:07"


def test_clone_source_must_be_inside_root_when_relative(root, ctx):
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        ops.get("clone_metadata").plan(ctx, [a], {"source": "../outside.jpg"}, {})


def test_courier_new_is_selectable_and_monospace_when_installed():
    from run.core import fonts
    if "Courier New" not in fonts.available_fonts():
        pytest.skip("Courier New not installed")
    font = fonts.load_font("Courier New", 20)
    # A monospace font gives every glyph the same advance width.
    assert font.getlength("iiiii") == font.getlength("WWWWW")


def test_font_registry_has_a_default_and_rejects_unknown_names(root, ctx):
    from run.core import fonts
    names_ = fonts.font_names()
    assert names_ and fonts.default_font_name() in names_
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        CAPTION.plan(ctx, [a], {"overwrite": True, "font": "../../etc/passwd", "captions": {"a.jpg": "x"}}, {})


def test_caption_font_choice_changes_output_and_is_listed(root, ctx, tmp_path):
    from run.core import fonts
    choices = [p for p in CAPTION.params if p.name == "font"][0].to_dict()
    assert choices["default"] == fonts.default_font_name()
    assert [c[0] for c in choices["choices"]] == fonts.font_names()
    other = next(n for n in fonts.font_names() if n != fonts.default_font_name())
    a = make_jpeg(root / "a.jpg", size=(600, 400))
    out = {}
    for label, font in (("default", None), ("other", other)):
        dest = tmp_path / label
        params = {"overwrite": False, "output_dir": str(dest), "captions": {"a.jpg": "Hello world"}}
        if font:
            params["font"] = font
        plan, rep = run(CAPTION, ctx, [a], params)
        assert rep.n_ok == 1 and plan.options["font"] == (font or fonts.default_font_name())
        out[label] = (dest / "a.jpg").read_bytes()
    assert out["default"] != out["other"]


def test_caption_fills_width_with_pad_sized_margins_before_wrapping(tmp_path):
    from run.core.burnin import render_caption
    src = tmp_path / "p.jpg"
    Image.new("RGB", (514, 700), (120, 110, 100)).save(src)
    text = ("Alfred Frank Salmon (1900) in about 1919. Probably wearing the uniform of a cadet in the "
            "Artists Rifles Officers' Training Corps (O.T.C.)")
    img, _, _ = render_caption(src, text)
    band = img.crop((0, 700, 514, img.height)).convert("L")
    left, top, right, bottom = band.point(lambda v: 255 if v < 140 else 0).getbbox()
    top_gap, bottom_gap = top, band.height - bottom
    assert top_gap == bottom_gap  # vertical gaps are equal
    # The old 80% rule left at least 51px (10%) each side; now only a word's worth of slack can remain.
    assert left < 40 and 514 - right < 40
    assert abs(left - (514 - right)) <= 2  # text is centred


def test_caption_font_defaults_to_courier_new_when_installed():
    from run.core import fonts
    if "Courier New" not in fonts.available_fonts():
        pytest.skip("Courier New not installed")
    assert fonts.default_font_name() == "Courier New"
    assert [p for p in CAPTION.params if p.name == "font"][0].to_dict()["default"] == "Courier New"
