from datetime import datetime

import pytest

from run.core import ops
from run.core.common import OperationError
from tests.conftest import make_jpeg, names, run

DIGITAL = ops.get("rename_digital")
FILM = ops.get("rename_film")


def test_digital_rename_numbers_shared_timestamps(root, ctx):
    taken = datetime(2020, 5, 17, 14, 30, 1)
    a = make_jpeg(root / "a.jpg", taken)
    b = make_jpeg(root / "b.jpg", taken)
    c = make_jpeg(root / "c.JPG", datetime(2021, 1, 2, 3, 4, 5))
    plan, rep = run(DIGITAL, ctx, [a, b, c], {"suffix": "Trip to Italy"})
    assert rep.n_ok == 3 and rep.n_failed == 0
    assert names(root) == ["20200517_143001_trip_to_italy_1.jpg", "20200517_143001_trip_to_italy_2.jpg",
                           "20210102_030405_trip_to_italy.jpg"]


def test_suffix_cannot_inject_path_components(root, ctx):
    a = make_jpeg(root / "a.jpg", datetime(2020, 1, 1, 1, 1, 1))
    plan, _ = run(DIGITAL, ctx, [a], {"suffix": "../../evil/name"})
    (only,) = names(root)
    assert only.startswith("20200101_010101_") and "/" not in only and only.endswith("evilname.jpg")
    assert not (root.parent / "evil").exists()


def test_existing_unrelated_file_is_never_overwritten(root, ctx):
    taken = datetime(2020, 5, 17, 14, 30, 1)
    a = make_jpeg(root / "a.jpg", taken)
    existing = make_jpeg(root / "20200517_143001.jpg", datetime(1999, 1, 1, 0, 0, 0))
    before = existing.read_bytes()
    plan, rep = run(DIGITAL, ctx, [a], {})
    assert [i.status for i in plan.items] == ["error"]
    assert not plan.ready
    assert existing.read_bytes() == before and (root / "a.jpg").exists()


def test_renames_that_chain_within_batch_work(root, ctx):
    # Sorted order shifts every file up by one, so each target is another file's current name.
    taken = datetime(2020, 1, 1, 10, 0, 0)
    files = [make_jpeg(root / f"20200101_100000_{i}.jpg", taken) for i in range(3)]
    plan, rep = run(DIGITAL, ctx, files, {})
    assert rep.n_failed == 0 and rep.n_ok == 3
    assert names(root) == ["20200101_100000_1.jpg", "20200101_100000_2.jpg", "20200101_100000_3.jpg"]


def test_already_standard_names_are_skipped(root, ctx):
    a = make_jpeg(root / "20200101_100000.jpg", datetime(2020, 1, 1, 10, 0, 0))
    plan, _ = run(DIGITAL, ctx, [a], {})
    assert plan.items[0].status == "skip" and not plan.ready


def test_raw_and_video_excluded_unless_requested(root, ctx):
    jpg = make_jpeg(root / "a.jpg", datetime(2020, 1, 1, 1, 1, 1))
    raw = root / "b.cr2"
    raw.write_bytes(b"not really raw")
    plan = DIGITAL.plan(ctx, [jpg, raw], {}, {})
    assert len(plan.items) == 1
    assert any("ignored" in w for w in plan.warnings)


def test_custom_date_must_be_valid(root, ctx):
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        DIGITAL.plan(ctx, [a], {"custom_date": "2020"}, {})


def test_film_rename_sequence(root, ctx):
    files = [make_jpeg(root / f"scan{i}.jpg") for i in range(3)]
    plan, rep = run(FILM, ctx, files, {"date": "197607", "suffix": "Beach"})
    assert rep.n_ok == 3
    assert names(root) == ["197607_beach_1.jpg", "197607_beach_2.jpg", "197607_beach_3.jpg"]


def test_film_requires_valid_date(root, ctx):
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        FILM.plan(ctx, [a], {"date": "1976-07"}, {})
    plan, rep = run(FILM, ctx, [a], {"date": "1976"})
    assert names(root) == ["1976.jpg"]


# ---- single-file rename (sidebar) ----

from run.core.rename import rename_file  # noqa: E402


def test_rename_file_keeps_extension_and_does_not_double_it(root):
    a = make_jpeg(root / "a.JPG")
    b = rename_file(a, "holiday")
    assert b.name == "holiday.JPG" and b.exists() and not a.exists()
    assert rename_file(b, "Holiday 2.jpg").name == "Holiday 2.JPG"  # typed extension is not repeated


@pytest.mark.parametrize("bad", ["", "   ", ".", "..", "a/b", "a\\b", "a:b", "a*b", "a?b", '"a"', "a|b", ".hidden",
                                 "trailing.", "bad\x00name", "x" * 300])
def test_rename_file_rejects_bad_names(root, bad):
    a = make_jpeg(root / "a.jpg")
    with pytest.raises(OperationError):
        rename_file(a, bad)
    assert names(root) == ["a.jpg"]


def test_rename_file_never_overwrites(root):
    a = make_jpeg(root / "a.jpg")
    other = make_jpeg(root / "b.jpg", size=(10, 10))
    before = other.read_bytes()
    with pytest.raises(OperationError):
        rename_file(a, "b")
    assert other.read_bytes() == before and a.exists()


def test_rename_file_same_name_and_case_only_rename(root):
    a = make_jpeg(root / "photo.jpg")
    assert rename_file(a, "photo") == a
    b = rename_file(a, "PHOTO")
    assert b.name == "PHOTO.jpg" and names(root) == ["PHOTO.jpg"]
