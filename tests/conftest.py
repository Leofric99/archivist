import os
import time

import pytest
from PIL import Image

from run.core.common import Context, Reporter


def make_jpeg(path, taken=None, size=(64, 48), color=(120, 80, 40), mtime=None):
    """Write a small JPEG, optionally with an EXIF DateTimeOriginal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    if taken:
        exif = Image.Exif()
        exif.get_ifd(0x8769)[36867] = taken.strftime("%Y:%m:%d %H:%M:%S")
        img.save(path, "JPEG", exif=exif)
    else:
        img.save(path, "JPEG")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def jpeg():
    return make_jpeg


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    return folder


@pytest.fixture
def ctx(root):
    return Context(root=root.resolve())


def run(op, ctx, files, params=None, answers=None, confirm=None):
    """Plan then apply an operation; returns (plan, reporter)."""
    plan = op.plan(ctx, files, params or {}, answers or {})
    rep = Reporter()
    if plan.ready:
        op.apply(ctx, plan, rep)
    return plan, rep


def names(folder):
    return sorted(p.name for p in folder.rglob("*") if p.is_file())


def wait_for_job(client, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/api/jobs/{job_id}").json()
        if snap["status"] != "running":
            return snap
        time.sleep(0.05)
    raise AssertionError("job did not finish")
