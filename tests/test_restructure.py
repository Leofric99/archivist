from datetime import datetime

import pytest

from run.core import ops
from run.core.restructure import parse_name
from tests.conftest import make_jpeg, run

RESTRUCTURE = ops.get("restructure")


def touch_media(folder, name):
    return make_jpeg(folder / name)


def test_parse_name_variants():
    assert parse_name("20200517_143001.jpg") == (datetime(2020, 5, 17), None)
    assert parse_name("20200517_143001_italy_2.jpg") == (datetime(2020, 5, 17), "Italy")
    assert parse_name("20200517_143001_summer_2019_1.jpg") == (datetime(2020, 5, 17), "Summer 2019")
    assert parse_name("200517_143001.jpg") == (datetime(2020, 5, 1), None)
    assert parse_name("IMG_0001.jpg") is None
    assert parse_name("20201399_143001.jpg") is None


def test_nonconforming_files_block_the_plan(root, ctx, tmp_path):
    touch_media(root, "20200517_143001.jpg")
    touch_media(root, "IMG_0001.jpg")
    plan = RESTRUCTURE.plan(ctx, [], {"dest_dir": str(tmp_path / "out")}, {})
    assert plan.errors and not plan.ready
    assert [i.source for i in plan.items] == ["IMG_0001.jpg"]


def test_copy_into_decade_year_month(root, ctx, tmp_path):
    touch_media(root, "20200517_143001.jpg")
    touch_media(root, "sub/20210102_010101.jpg")
    out = tmp_path / "out"
    plan, rep = run(RESTRUCTURE, ctx, [], {"dest_dir": str(out)})
    assert rep.n_ok == 2 and rep.n_failed == 0
    assert (out / "2020s" / "2020" / "5. May" / "20200517_143001.jpg").exists()
    assert (out / "2020s" / "2021" / "1. January" / "20210102_010101.jpg").exists()
    assert (root / "20200517_143001.jpg").exists()  # copy mode leaves sources alone


def test_event_folder_needs_threshold(root, ctx, tmp_path):
    for i in range(10):
        touch_media(root, f"20200517_1430{i:02d}_italy.jpg")
    touch_media(root, "20200601_100000_rome.jpg")
    out = tmp_path / "out"
    run(RESTRUCTURE, ctx, [], {"dest_dir": str(out)})
    assert (out / "2020s" / "2020" / "Italy").is_dir()
    assert (out / "2020s" / "2020" / "6. June" / "20200601_100000_rome.jpg").exists()


def test_distant_dates_in_one_event_ask_a_question(root, ctx, tmp_path):
    touch_media(root, "20150101_000000_wedding.jpg")
    touch_media(root, "20200101_000000_wedding.jpg")
    params = {"dest_dir": str(tmp_path / "out")}
    plan = RESTRUCTURE.plan(ctx, [], params, {})
    assert len(plan.questions) == 1 and not plan.ready
    qid = plan.questions[0]["id"]
    answered = RESTRUCTURE.plan(ctx, [], params, {qid: True})
    assert not answered.questions and answered.ready


@pytest.mark.parametrize("where", ["inside", "parent", "home", "root"])
def test_dangerous_destinations_are_rejected(root, ctx, where):
    touch_media(root, "20200517_143001.jpg")
    from pathlib import Path
    dest = {"inside": root / "out", "parent": root.parent, "home": Path.home(), "root": Path("/")}[where]
    plan = RESTRUCTURE.plan(ctx, [], {"dest_dir": str(dest)}, {})
    assert plan.errors and not plan.ready
    assert (root / "20200517_143001.jpg").exists()


def test_existing_destination_contents_require_confirmation(root, ctx, tmp_path):
    touch_media(root, "20200517_143001.jpg")
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("old")
    plan = RESTRUCTURE.plan(ctx, [], {"dest_dir": str(out)}, {})
    assert plan.confirmation == {"message": plan.confirmation["message"], "expected": "out"}
    run(RESTRUCTURE, ctx, [], {"dest_dir": str(out)})
    assert not (out / "old.txt").exists()


def test_in_place_moves_files_and_keeps_non_media_folders(root, ctx):
    touch_media(root, "a/20200517_143001.jpg")
    (root / "docs").mkdir()
    (root / "docs" / "notes.txt").write_text("keep me")
    (root / "empty").mkdir()
    plan = RESTRUCTURE.plan(ctx, [], {"dest_dir": str(root)}, {})
    assert plan.confirmation["expected"] == root.name
    _, rep = run(RESTRUCTURE, ctx, [], {"dest_dir": str(root)})
    assert (root / "2020s" / "2020" / "5. May" / "20200517_143001.jpg").exists()
    assert not (root / "a").exists()  # emptied by the move
    assert (root / "docs" / "notes.txt").read_text() == "keep me"  # never deleted
    assert not (root / "empty").exists()  # empty folders are tidied away
