import base64
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from run.desktop import DesktopBridge, _desktop_html, _enable_file_drop, _resource_path
from tests.conftest import make_jpeg


def test_desktop_bridge_dispatches_api_calls_in_process(root):
    bridge = DesktopBridge(root.resolve())
    try:
        response = bridge.request("GET", "/api/state")
        assert response["status"] == 200
        state = json.loads(base64.b64decode(response["body"]))
        assert state["root"] == str(root.resolve())
        assert bridge.request("POST", "/api/root", {"path": str(root.resolve())})["status"] == 200
    finally:
        bridge._close()


def test_desktop_media_url_uses_confined_video_paths(root):
    video = root / "clip.mp4"
    video.write_bytes(b"video")
    bridge = DesktopBridge(root.resolve())
    try:
        bridge.request("POST", "/api/root", {"path": str(root.resolve())})
        assert bridge.media_url("clip.mp4") == video.as_uri()
        with pytest.raises(HTTPException):
            bridge.media_url("../outside.mp4")
    finally:
        bridge._close()


def test_desktop_bridge_rejects_non_api_requests():
    bridge = DesktopBridge()
    try:
        with pytest.raises(ValueError):
            bridge.request("GET", "/")
    finally:
        bridge._close()


def test_dropped_images_keep_identity_after_rename_and_support_save_destinations(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    photo = make_jpeg(source / "scan.jpg")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    bridge = DesktopBridge()
    try:
        added = bridge.add_files([str(photo), str(source / "not-an-image.txt")])
        assert added == {"added": 1, "skipped": 1}

        listing = json.loads(base64.b64decode(bridge.request("GET", "/api/files")["body"]))
        item = listing["files"][0]
        identity = item["path"]
        assert listing["collection"] is True
        assert item["location"] == str(photo.resolve())

        renamed = json.loads(base64.b64decode(bridge.request(
            "POST", "/api/rename", {"path": identity, "name": "renamed"}
        )["body"]))
        assert renamed == {"path": identity, "name": "renamed.jpg"}
        assert (source / "renamed.jpg").is_file()
        assert bridge.request("GET", f"/api/thumb?path={identity}")["status"] == 200

        same_folder = json.loads(base64.b64decode(bridge.request(
            "POST", "/api/ops/burnin_basic/plan",
            {"paths": [identity], "params": {"text": "test"}},
        )["body"]))
        assert same_folder["ready"]
        assert Path(same_folder["items"][0]["source"]) == source / "renamed.jpg"
        assert Path(same_folder["items"][0]["target"]) == source / "renamed_archivist.jpg"

        save_elsewhere = json.loads(base64.b64decode(bridge.request(
            "POST", "/api/ops/burnin_basic/plan",
            {"paths": [identity], "params": {"text": "test", "output_dir": str(elsewhere)}},
        )["body"]))
        assert save_elsewhere["ready"]
        assert Path(save_elsewhere["items"][0]["target"]) == elsewhere / "renamed.jpg"
        assert bridge.request("GET", "/api/thumb?path=not-a-dropped-file")["status"] == 400
    finally:
        bridge._close()


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_webview_drop_event_uses_native_full_file_paths(monkeypatch, tmp_path, platform):
    from webview.dom import DOMEventHandler

    photo = make_jpeg(tmp_path / "drop.jpg")

    class LoadedEvent:
        callback = None

        def __iadd__(self, callback):
            self.callback = callback
            return self

    class DropTarget:
        name = None
        handler = None

        def on(self, name, handler):
            self.name = name
            self.handler = handler

    class Window:
        def __init__(self):
            self.events = type("Events", (), {"loaded": LoadedEvent()})()
            self.drop_target = DropTarget()
            self.scripts = []
            self.dom = type("DOM", (), {"get_element": lambda _, selector: self.drop_target if selector == "body" else None})()

        def evaluate_js(self, script):
            self.scripts.append(script)

    monkeypatch.setattr("run.desktop.sys.platform", platform)
    window = Window()
    bridge = DesktopBridge()
    try:
        _enable_file_drop(window, bridge)
        window.events.loaded.callback()
        assert window.drop_target.name == "drop"
        assert isinstance(window.drop_target.handler, DOMEventHandler)
        assert window.drop_target.handler.prevent_default
        window.drop_target.handler.callback({
            "dataTransfer": {"files": [{"name": photo.name, "pywebviewFullPath": str(photo)}]},
        })
        data = json.loads(base64.b64decode(bridge.request("GET", "/api/files")["body"]))
        assert data["files"][0]["location"] == str(photo.resolve())
        assert window.scripts[-1].startswith("window.archivistFilesDropped(")
    finally:
        bridge._close()


def test_desktop_html_uses_local_assets_and_marks_native_bridge():
    static_dir = _resource_path("run/web/static")
    html = _desktop_html(static_dir)
    assert f'<base href="{static_dir.resolve().as_uri()}/">' in html
    assert '<html lang="en" data-desktop="true">' in html
    assert 'href="style.css"' in html
    assert 'src="app.js"' in html


@pytest.mark.parametrize("platform, allows_eval", [("darwin", True), ("win32", False)])
def test_desktop_html_allows_eval_only_on_macos(monkeypatch, platform, allows_eval):
    monkeypatch.setattr("run.desktop.sys.platform", platform)
    html = _desktop_html(_resource_path("run/web/static"))
    assert ("'unsafe-eval'" in html) is allows_eval
