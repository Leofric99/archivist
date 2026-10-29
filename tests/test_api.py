import shutil
import subprocess
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from run.web.app import create_app
from tests.conftest import make_jpeg, names, wait_for_job

PORT = 5123
TOKEN = "test-token-123"
ORIGIN = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def client(root):
    app = create_app(TOKEN, PORT, root.resolve())
    with TestClient(app, base_url=ORIGIN) as c:
        c.cookies.set("archivist_token", TOKEN)
        c.headers["Origin"] = ORIGIN
        yield c


def post(client, url, /, **body):
    return client.post(url, json=body)


# ---- access control ----


def test_api_requires_the_token_cookie(root):
    app = create_app(TOKEN, PORT, root)
    with TestClient(app, base_url=ORIGIN) as anon:
        assert anon.get("/api/state").status_code == 401
        assert anon.get("/").status_code == 403


def test_token_in_url_sets_cookie_and_redirects(root):
    app = create_app(TOKEN, PORT, root)
    with TestClient(app, base_url=ORIGIN) as anon:
        bad = anon.get("/?token=wrong", follow_redirects=False)
        assert bad.status_code == 403
        ok = anon.get(f"/?token={TOKEN}", follow_redirects=False)
        assert ok.status_code == 303 and "archivist_token" in ok.headers["set-cookie"]
        assert "samesite=strict" in ok.headers["set-cookie"].lower()
        assert anon.get("/").status_code == 200


def test_foreign_host_header_is_refused(client):
    assert client.get("/api/state", headers={"Host": "evil.example:5123"}).status_code == 403


def test_mutations_need_a_matching_origin(client):
    assert client.post("/api/root", json={"path": "/"}, headers={"Origin": "http://evil.example"}).status_code == 403
    no_origin = client.post("/api/root", json={"path": "/"}, headers={"Origin": ""})
    assert no_origin.status_code == 403


# ---- listing and path confinement ----


def test_lists_supported_files_only(client, root):
    make_jpeg(root / "a.jpg")
    make_jpeg(root / "sub" / "b.jpg")
    (root / "notes.txt").write_text("x")
    (root / ".hidden.jpg").write_bytes(b"x")
    files = client.get("/api/files").json()["files"]
    assert sorted(f["path"] for f in files) == ["a.jpg", "sub/b.jpg"]
    flat = client.get("/api/files?subdirs=false").json()["files"]
    assert [f["path"] for f in flat] == ["a.jpg"]


@pytest.mark.parametrize("endpoint", ["thumb", "preview", "info", "file"])
def test_file_endpoints_cannot_escape_the_root(client, root, tmp_path, endpoint):
    secret = make_jpeg(tmp_path / "secret.jpg")
    for attempt in ("../secret.jpg", str(secret)):
        assert client.get(f"/api/{endpoint}", params={"path": attempt}).status_code == 400


def test_symlink_escape_is_refused(client, root, tmp_path):
    secret = make_jpeg(tmp_path / "secret.jpg")
    (root / "link.jpg").symlink_to(secret)
    assert client.get("/api/thumb", params={"path": "link.jpg"}).status_code == 400


def test_thumbnail_and_info_are_served(client, root):
    make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3), size=(800, 600))
    thumb = client.get("/api/thumb", params={"path": "a.jpg"})
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    info = client.get("/api/info", params={"path": "a.jpg"}).json()
    titles = [s["title"] for s in info["sections"]]
    assert "File" in titles and "Image" in titles


def test_browse_lists_only_folders(client, root):
    (root / "child").mkdir()
    make_jpeg(root / "a.jpg")
    data = client.get("/api/browse", params={"path": str(root)}).json()
    assert data["folders"] == ["child"]


def test_changing_root(client, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    make_jpeg(other / "x.jpg")
    assert post(client, "/api/root", path=str(other)).status_code == 200
    assert [f["path"] for f in client.get("/api/files").json()["files"]] == ["x.jpg"]
    assert post(client, "/api/root", path=str(tmp_path / "missing")).status_code == 400


# ---- plan / apply flow ----


def test_plan_then_apply_rename(client, root):
    make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3))
    plan = post(client, "/api/ops/rename_digital/plan", paths=["a.jpg"], params={"suffix": "Italy"}).json()
    assert plan["ready"] and plan["items"][0]["target"] == "20200517_010203_italy.jpg"
    job = post(client, "/api/ops/rename_digital/apply", plan_id=plan["plan_id"]).json()
    snap = wait_for_job(client, job["job_id"])
    assert snap["status"] == "done" and snap["counts"]["ok"] == 1
    assert names(root) == ["20200517_010203_italy.jpg"]


def test_plan_is_single_use(client, root):
    make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3))
    plan = post(client, "/api/ops/rename_digital/plan", paths=["a.jpg"], params={}).json()
    first = post(client, "/api/ops/rename_digital/apply", plan_id=plan["plan_id"])
    wait_for_job(client, first.json()["job_id"])
    assert post(client, "/api/ops/rename_digital/apply", plan_id=plan["plan_id"]).status_code == 400


def test_plan_rejects_missing_required_and_bad_paths(client, root):
    make_jpeg(root / "a.jpg")
    assert post(client, "/api/ops/rename_film/plan", paths=["a.jpg"], params={}).status_code == 400
    assert post(client, "/api/ops/rename_digital/plan", paths=[], params={}).status_code == 400
    assert post(client, "/api/ops/rename_digital/plan", paths=["../x.jpg"], params={}).status_code == 400
    assert post(client, "/api/ops/nope/plan", paths=["a.jpg"], params={}).status_code == 404


def test_apply_with_errors_is_refused(client, root):
    make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3))
    make_jpeg(root / "20200517_010203.jpg", datetime(1990, 1, 1, 0, 0, 0))
    plan = post(client, "/api/ops/rename_digital/plan", paths=["a.jpg"], params={}).json()
    assert not plan["ready"]
    assert post(client, "/api/ops/rename_digital/apply", plan_id=plan["plan_id"]).status_code == 400


def test_restructure_requires_typed_confirmation(client, root, tmp_path):
    make_jpeg(root / "20200517_143001.jpg")
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("old")
    plan = post(client, "/api/ops/restructure/plan", params={"dest_dir": str(out)}).json()
    assert plan["confirmation"]["expected"] == "out"
    refused = post(client, "/api/ops/restructure/apply", plan_id=plan["plan_id"], confirm="yes")
    assert refused.status_code == 400 and (out / "old.txt").exists()
    job = post(client, "/api/ops/restructure/apply", plan_id=plan["plan_id"], confirm="out").json()
    assert wait_for_job(client, job["job_id"])["status"] == "done"
    assert not (out / "old.txt").exists()
    assert (out / "2020s" / "2020" / "5. May" / "20200517_143001.jpg").exists()


def test_burnin_preview_returns_jpeg(client, root):
    make_jpeg(root / "a.jpg", size=(500, 400))
    res = post(client, "/api/ops/burnin_basic/preview", path="a.jpg", params={"text": "Hi"})
    assert res.status_code == 200 and res.content[:2] == b"\xff\xd8"


def test_event_stream_reports_completion(client, root):
    make_jpeg(root / "a.jpg", datetime(2020, 5, 17, 1, 2, 3))
    plan = post(client, "/api/ops/rename_digital/plan", paths=["a.jpg"], params={}).json()
    job = post(client, "/api/ops/rename_digital/apply", plan_id=plan["plan_id"]).json()
    with client.stream("GET", f"/api/jobs/{job['job_id']}/events") as stream:
        body = "".join(stream.iter_text())
    assert '"status": "done"' in body


# ---- video (uses the real ffmpeg when available) ----


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed")
def test_video_burn_in_end_to_end(client, root, tmp_path):
    video = root / "clip_20200517_101112.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1:r=10",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    out = tmp_path / "burned"
    plan = post(client, "/api/ops/burnin_video/plan", paths=[video.name],
                params={"text": "Test", "output_dir": str(out)}).json()
    assert plan["ready"], plan
    job = post(client, "/api/ops/burnin_video/apply", plan_id=plan["plan_id"]).json()
    snap = wait_for_job(client, job["job_id"], timeout=60)
    assert snap["status"] == "done" and snap["counts"]["failed"] == 0, snap["logs"]
    assert (out / video.name).stat().st_size > 0
    assert not list(out.glob(".*tmp*"))


def test_logo_and_favicon_are_served_and_referenced(root):
    app = create_app(TOKEN, PORT, root)
    with TestClient(app, base_url=ORIGIN) as c:
        for name in ("logo.png", "favicon.png"):
            res = c.get(f"/static/{name}")
            assert res.status_code == 200 and res.headers["content-type"] == "image/png"
        assert c.get("/static/crop-editor.js").status_code == 200
        c.cookies.set("archivist_token", TOKEN)
        assert '<base href="/static/">' in c.get("/").text
        assert 'src="logo.png"' in c.get("/").text


# ---- sidebar rename ----


def test_rename_endpoint_renames_inside_subfolder_and_returns_new_path(client, root):
    make_jpeg(root / "sub" / "a.jpg")
    res = post(client, "/api/rename", path="sub/a.jpg", name="Grandma")
    assert res.status_code == 200 and res.json() == {"path": "sub/Grandma.jpg", "name": "Grandma.jpg"}
    assert names(root) == ["Grandma.jpg"]


def test_rename_endpoint_validation_and_confinement(client, root, tmp_path):
    make_jpeg(root / "a.jpg")
    make_jpeg(root / "b.jpg")
    secret = make_jpeg(tmp_path / "secret.jpg")
    assert post(client, "/api/rename", path="a.jpg", name="b").status_code == 400  # collision
    assert post(client, "/api/rename", path="a.jpg", name="../evil").status_code == 400
    assert post(client, "/api/rename", path="../secret.jpg", name="x").status_code == 400
    assert post(client, "/api/rename", path=str(secret), name="x").status_code == 400
    assert post(client, "/api/rename", path="nope.jpg", name="x").status_code == 404
    assert secret.exists() and names(root) == ["a.jpg", "b.jpg"]


def test_rename_endpoint_refuses_symlinks(client, root):
    target = make_jpeg(root / "real.jpg")
    (root / "link.jpg").symlink_to(target)
    assert post(client, "/api/rename", path="link.jpg", name="renamed").status_code == 400
    assert target.exists()


def test_rename_endpoint_needs_origin_and_cookie(root):
    app = create_app(TOKEN, PORT, root)
    make_jpeg(root / "a.jpg")
    with TestClient(app, base_url=ORIGIN) as anon:
        assert anon.post("/api/rename", json={"path": "a.jpg", "name": "x"}).status_code == 401
        anon.cookies.set("archivist_token", TOKEN)
        assert anon.post("/api/rename", json={"path": "a.jpg", "name": "x"}).status_code == 403  # no Origin
    assert names(root) == ["a.jpg"]


def test_page_has_context_menu_and_rename_hooks(root):
    app = create_app(TOKEN, PORT, root)
    with TestClient(app, base_url=ORIGIN) as c:
        c.cookies.set("archivist_token", TOKEN)
        html = c.get("/").text
        js = c.get("/static/app.js").text
    assert 'id="ctx-menu"' in html and 'id="side"' in html
    assert "contextmenu" in js and "/rename" in js
