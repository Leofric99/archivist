import pytest
from PIL import Image

from run.core import ops
from run.core.common import OperationError
from run.core.crop import centred_box, oriented_size, parse_ratio, pixel_box
from tests.conftest import make_jpeg, names, run

CROP = ops.get("crop")


def size_of(path):
    with Image.open(path) as img:
        return img.size


@pytest.mark.parametrize("text,expected", [("3:2", 1.5), ("16x9", 16 / 9), (" 1 : 1 ", 1.0), ("1.5", 1.5), ("", None)])
def test_parse_ratio(text, expected):
    assert parse_ratio(text) == pytest.approx(expected) if expected else parse_ratio(text) is None


@pytest.mark.parametrize("text", ["abc", "0:3", "3:0", "-1:2", "3:"])
def test_parse_ratio_rejects_garbage(text):
    with pytest.raises(OperationError):
        parse_ratio(text)


def test_centred_box_has_requested_ratio_and_is_centred():
    assert centred_box((4000, 3000), 1.0) == (500, 0, 3500, 3000)
    assert centred_box((3000, 4000), 1.0) == (0, 500, 3000, 3500)
    x0, y0, x1, y1 = centred_box((4000, 3000), 16 / 9)
    assert (x1 - x0, y1 - y0) == (4000, 2250) and y0 == 375


def test_pixel_box_validation():
    assert pixel_box([0.25, 0.25, 0.5, 0.5], (400, 200)) == (100, 50, 300, 150)
    for bad in ([0.5, 0.5, 0.6, 0.2], [-0.2, 0, 0.5, 0.5], [0, 0, 0, 1], [0, 0, 0.001, 0.5], "abc", [0, 0, float("nan"), 1]):
        with pytest.raises(OperationError):
            pixel_box(bad, (400, 200))


def test_manual_crop_writes_exact_region_to_output_and_keeps_original(root, ctx, tmp_path):
    a = root / "sub" / "a.jpg"
    img = Image.new("RGB", (400, 200), (255, 0, 0))
    img.paste((0, 0, 255), (200, 0, 400, 200))
    a.parent.mkdir()
    img.save(a, "JPEG", quality=100)
    original = a.read_bytes()
    out = tmp_path / "out"
    params = {"overwrite": False, "output_dir": str(out), "crops": {"sub/a.jpg": [0.5, 0, 0.5, 1]}}
    plan, rep = run(CROP, ctx, [a], params)
    assert rep.n_ok == 1, rep
    assert plan.items[0].note.startswith("400×200 → 200×200")
    result = out / "sub" / "a.jpg"
    assert size_of(result) == (200, 200) and a.read_bytes() == original
    with Image.open(result) as r:
        red, green, blue = r.convert("RGB").getpixel((100, 100))
        assert blue > 200 and red < 60


def test_crop_follows_exif_orientation(root, ctx, tmp_path):
    a = root / "rot.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways: displays rotated, so 300x400 on screen
    Image.new("RGB", (400, 300), (10, 200, 10)).save(a, "JPEG", exif=exif)
    assert oriented_size(a) == (300, 400)
    out = tmp_path / "out"
    plan, rep = run(CROP, ctx, [a], {"overwrite": False, "output_dir": str(out), "crops": {"rot.jpg": [0, 0, 1, 0.5]}})
    assert rep.n_ok == 1, rep
    with Image.open(out / "rot.jpg") as r:
        assert r.size == (300, 200)
        assert r.getexif().get(0x0112) in (None, 1)  # already upright; must not be rotated again


def test_ratio_centre_crops_files_without_manual_crop(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg", size=(400, 300))
    b = make_jpeg(root / "b.jpg", size=(400, 300))
    params = {"overwrite": False, "output_dir": str(tmp_path / "o"), "ratio": "1:1", "crops": {"a.jpg": [0, 0, 0.5, 0.5]}}
    plan, rep = run(CROP, ctx, [a, b], params)
    assert rep.n_ok == 2
    assert size_of(tmp_path / "o" / "a.jpg") == (200, 150)  # manual box wins
    assert size_of(tmp_path / "o" / "b.jpg") == (300, 300)


def test_uncropped_photos_are_skipped_without_ratio(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg")
    plan = CROP.plan(ctx, [a], {"overwrite": False, "output_dir": str(tmp_path / "o")}, {})
    assert plan.items[0].status == "skip" and not plan.ready


def test_overwrite_replaces_in_place_and_refuses_same_folder_output(root, ctx):
    a = make_jpeg(root / "a.jpg", size=(400, 300))
    bad = CROP.plan(ctx, [a], {"overwrite": False, "output_dir": str(root), "ratio": "1:1"}, {})
    assert bad.errors and not bad.ready
    plan, rep = run(CROP, ctx, [a], {"overwrite": True, "ratio": "1:1"})
    assert rep.n_ok == 1 and size_of(a) == (300, 300)
    assert names(root) == ["a.jpg"]


def test_bad_boxes_become_item_errors_not_crashes(root, ctx, tmp_path):
    a = make_jpeg(root / "a.jpg")
    plan = CROP.plan(ctx, [a], {"overwrite": True, "crops": {"a.jpg": [0.9, 0.9, 0.5, 0.5]}}, {})
    assert plan.items[0].status == "error" and not plan.ready


def test_unsupported_format_skipped(root, ctx):
    gif = root / "a.gif"
    Image.new("P", (40, 40)).save(gif)
    plan = CROP.plan(ctx, [gif], {"overwrite": True, "ratio": "1:1"}, {})
    assert plan.items[0].status == "skip"


def test_crop_via_api_with_manual_boxes(root):
    from fastapi.testclient import TestClient
    from run.web.app import create_app
    from tests.conftest import wait_for_job
    origin = "http://127.0.0.1:5124"
    make_jpeg(root / "a.jpg", size=(400, 200))
    with TestClient(create_app("t", 5124, root.resolve()), base_url=origin) as c:
        c.cookies.set("archivist_token", "t")
        c.headers["Origin"] = origin
        assert [o for o in c.get("/api/state").json()["ops"] if o["id"] == "crop"][0]["editor"] == "crop"
        body = {"paths": ["a.jpg"], "params": {"overwrite": True, "crops": {"a.jpg": [0, 0, 0.5, 1]}}}
        plan = c.post("/api/ops/crop/plan", json=body).json()
        assert plan["ready"] and "400×200 → 200×200" in plan["items"][0]["note"]
        job = c.post("/api/ops/crop/apply", json={"plan_id": plan["plan_id"]}).json()
        assert wait_for_job(c, job["job_id"])["status"] == "done"
    assert size_of(root / "a.jpg") == (200, 200)
