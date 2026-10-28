from datetime import datetime

import pytest

from run.core import dates


def test_exif_date_wins(root, jpeg):
    p = jpeg(root / "IMG_9999.jpg", taken=datetime(2020, 5, 17, 14, 30, 1))
    assert dates.photo_date(p) == datetime(2020, 5, 17, 14, 30, 1)


def test_filename_date_used_without_exif(root, jpeg):
    p = jpeg(root / "holiday_20190203_101112.jpg")
    assert dates.photo_date(p) == datetime(2019, 2, 3, 10, 11, 12)
    q = jpeg(root / "scan_20180401.jpg")
    assert dates.photo_date(q) == datetime(2018, 4, 1)


def test_mtime_is_last_resort(root, jpeg):
    p = jpeg(root / "plain.jpg", mtime=datetime(2001, 2, 3, 4, 5, 6).timestamp())
    assert dates.photo_date(p) == datetime(2001, 2, 3, 4, 5, 6)


def test_formatting():
    assert dates.format_datetime(datetime(2020, 1, 1)) == "1st January 2020"
    assert dates.format_datetime(datetime(2020, 3, 12)) == "12th March 2020"
    assert dates.format_datetime(datetime(2020, 3, 23)) == "23rd March 2020"
    assert dates.format_custom_date("202001") == "January 2020"
    assert dates.format_custom_date("1999") == "1999"


@pytest.mark.parametrize("value", ["", "202013", "20200230", "abcd", "2020010"])
def test_validate_rejects_bad_dates(value):
    with pytest.raises(ValueError):
        dates.validate_date_string(value)


def test_validate_accepts_partial_dates():
    assert dates.validate_date_string("2020") == "2020"
    assert dates.validate_date_string("202002") == "202002"
    assert dates.validate_date_string("20200229") == "20200229"
